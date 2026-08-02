from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import ceil
from threading import Event, Lock, Thread
from time import perf_counter
from typing import Callable, Optional

import cv2
import numpy as np

from ai.yolo_detector import FrameDetections
from workers.contracts import FramePacket
from workers.frame_buffer import LatestFrameBuffer
from workers.tracker import IoUTracker, TrackedTarget
from workers.candidate_producer import CandidateEventProducer, CandidateEvent
from workers.roi import ROI


@dataclass(frozen=True)
class InferenceResult:
    packet: FramePacket
    detections: FrameDetections
    annotated_frame: np.ndarray
    tracks: tuple[TrackedTarget, ...] = ()
    events: tuple[CandidateEvent, ...] = ()
    rois: tuple[ROI, ...] = ()


@dataclass
class _TaskMetrics:
    processed_frames: int = 0
    failed_frames: int = 0
    stale_frames_discarded: int = 0
    person_count: int = 0
    last_frame_index: Optional[int] = None
    preprocess_ms: float = 0.0
    inference_ms: float = 0.0
    postprocess_ms: float = 0.0
    end_to_end_ms: float = 0.0
    inference_fps: float = 0.0
    last_processed_at: Optional[str] = None
    last_error: Optional[str] = None


class InferenceWorker:
    def __init__(
        self,
        *,
        detector=None,
        detector_factory: Optional[Callable] = None,
        idle_wait_seconds: float = 0.01,
        latency_window_size: int = 200,
    ) -> None:
        if (detector is None) == (detector_factory is None):
            raise ValueError("Provide exactly one detector or detector_factory")
        self._detector = detector
        self._detector_factory = detector_factory
        self._idle_wait_seconds = max(0.001, float(idle_wait_seconds))
        self._latency_window_size = max(1, int(latency_window_size))
        self._buffers: dict[int, LatestFrameBuffer] = {}
        self._task_order: deque[int] = deque()
        self._metrics: dict[int, _TaskMetrics] = {}
        self._latencies: dict[int, deque[float]] = {}
        self._processing_seconds: dict[int, float] = {}
        self._results: dict[int, InferenceResult] = {}
        self._trackers: dict[int, IoUTracker] = {}
        self._producers: dict[int, CandidateEventProducer] = {}
        self._lock = Lock()
        self._detector_lock = Lock()
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def register(self, task_id: int, buffer: LatestFrameBuffer) -> None:
        with self._lock:
            if task_id not in self._buffers:
                self._task_order.append(task_id)
            self._buffers[task_id] = buffer
            self._metrics.setdefault(task_id, _TaskMetrics())
            self._processing_seconds.setdefault(task_id, 0.0)
            self._latencies.setdefault(
                task_id, deque(maxlen=self._latency_window_size)
            )
            self._trackers[task_id] = IoUTracker()
            self._producers[task_id] = CandidateEventProducer()

    def unregister(self, task_id: int) -> None:
        with self._lock:
            self._buffers.pop(task_id, None)
            self._metrics.pop(task_id, None)
            self._latencies.pop(task_id, None)
            self._processing_seconds.pop(task_id, None)
            self._results.pop(task_id, None)
            self._trackers.pop(task_id, None)
            self._producers.pop(task_id, None)
            self._task_order = deque(
                item for item in self._task_order if item != task_id
            )

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self.run,
                name="central-inference",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, timeout_seconds))

    def run(self) -> None:
        while not self._stop_event.is_set():
            if self.process_next() is None:
                self._stop_event.wait(self._idle_wait_seconds)

    def process_next(self) -> Optional[int]:
        selected = self._next_buffer()
        if selected is None:
            return None
        task_id, buffer = selected
        packet, discarded = buffer.get_latest()
        if packet is None:
            return None
        self._record_discarded(task_id, discarded)
        try:
            detector = self._get_detector()
            inference_started_at = perf_counter()
            detections = detector.detect(
                packet.frame,
                frame_index=packet.frame_index,
                timestamp_ms=packet.source_timestamp_ms,
            )
            now = datetime.now(timezone.utc)
            end_to_end_ms = max(
                0.0, (now - packet.captured_at).total_seconds() * 1000.0
            )
            tracks = self._trackers[task_id].update(detections) if task_id in self._trackers else ()
            producer = self._producers.get(task_id)
            events = producer.update(task_id, packet.run_id, tracks, packet.frame_index, packet.source_timestamp_ms) if producer and tracks else ()
            rois = producer.rois if producer else ()
            result = InferenceResult(
                packet=packet,
                detections=detections,
                annotated_frame=self._draw_detections(packet.frame, detections, tracks, rois),
                tracks=tracks,
                events=events,
                rois=rois,
            )
            processing_seconds = max(
                perf_counter() - inference_started_at,
                detections.total_ms / 1000.0,
            )
            self._record_success(
                task_id, result, end_to_end_ms, processing_seconds, now
            )
        except Exception as exc:
            self._record_failure(task_id, str(exc))
        return task_id

    def latest_result(self, task_id: int) -> Optional[InferenceResult]:
        with self._lock:
            return self._results.get(task_id)

    def task_snapshot(self, task_id: int) -> Optional[dict]:
        with self._lock:
            metrics = self._metrics.get(task_id)
            if metrics is None:
                return None
            snapshot = asdict(metrics)
            latencies = list(self._latencies[task_id])
        snapshot["end_to_end_p95_ms"] = self._percentile(latencies, 0.95)
        return snapshot

    def tracker_snapshot(self, task_id: int) -> Optional[dict]:
        tracker = self._trackers.get(task_id)
        if tracker is None:
            return None
        return tracker.snapshot()

    def producer_snapshot(self, task_id: int) -> Optional[dict]:
        producer = self._producers.get(task_id)
        if producer is None:
            return None
        return producer.snapshot()

    def _next_buffer(self) -> Optional[tuple[int, LatestFrameBuffer]]:
        with self._lock:
            attempts = len(self._task_order)
            for _ in range(attempts):
                task_id = self._task_order.popleft()
                self._task_order.append(task_id)
                buffer = self._buffers.get(task_id)
                if buffer is not None and buffer.size > 0:
                    return task_id, buffer
        return None

    def _get_detector(self):
        with self._detector_lock:
            if self._detector is None:
                self._detector = self._detector_factory()
            return self._detector

    def _record_discarded(self, task_id: int, discarded: int) -> None:
        with self._lock:
            metrics = self._metrics.get(task_id)
            if metrics is not None:
                metrics.stale_frames_discarded += discarded

    def _record_success(
        self,
        task_id: int,
        result: InferenceResult,
        end_to_end_ms: float,
        processing_seconds: float,
        now: datetime,
    ) -> None:
        with self._lock:
            metrics = self._metrics.get(task_id)
            if metrics is None:
                return
            metrics.processed_frames += 1
            metrics.person_count = len(result.detections.detections)
            metrics.last_frame_index = result.packet.frame_index
            metrics.preprocess_ms = result.detections.preprocess_ms
            metrics.inference_ms = result.detections.inference_ms
            metrics.postprocess_ms = result.detections.postprocess_ms
            metrics.end_to_end_ms = end_to_end_ms
            metrics.last_processed_at = now.isoformat()
            metrics.last_error = None
            self._processing_seconds[task_id] += processing_seconds
            metrics.inference_fps = (
                metrics.processed_frames / self._processing_seconds[task_id]
            )
            self._latencies[task_id].append(end_to_end_ms)
            self._results[task_id] = result

    def _record_failure(self, task_id: int, message: str) -> None:
        with self._lock:
            metrics = self._metrics.get(task_id)
            if metrics is not None:
                metrics.failed_frames += 1
                metrics.last_error = message

    @staticmethod
    def _draw_detections(
        frame: np.ndarray, detections: FrameDetections,
        tracks: tuple[TrackedTarget, ...] = (),
        events: tuple[CandidateEvent, ...] = (),
        rois: tuple[ROI, ...] = ()
    ) -> np.ndarray:
        annotated = frame.copy()
        height, width = annotated.shape[:2]
        for detection in detections.detections:
            x1, y1, x2, y2 = detection.xyxy
            left = max(0, min(width - 1, int(round(x1))))
            top = max(0, min(height - 1, int(round(y1))))
            right = max(0, min(width - 1, int(round(x2))))
            bottom = max(0, min(height - 1, int(round(y2))))
            cv2.rectangle(annotated, (left, top), (right, bottom), (0, 255, 0), 2)
            label = f"{detection.class_name} {detection.confidence:.2f}"
            cv2.putText(
                annotated,
                label,
                (left, max(12, top - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
        # Draw ROI polygons
        for roi in rois:
            pts = np.array([(int(x), int(y)) for x, y in roi.points], dtype=np.int32)
            cv2.polylines(annotated, [pts], isClosed=True, color=roi.color, thickness=2)
            label_x, label_y = int(roi.points[0][0]), max(12, int(roi.points[0][1]) - 5)
            cv2.putText(annotated, roi.name, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, roi.color, 2, cv2.LINE_AA)

        # Draw track IDs and trajectory lines
        for t_target in tracks:
            hue = (t_target.track_id * 37) % 180
            color = tuple(int(c) for c in cv2.cvtColor(np.uint8([[[hue, 255, 255]]]), cv2.COLOR_HSV2BGR)[0, 0])
            x1, y1, x2, y2 = (int(round(v)) for v in t_target.xyxy)
            state_label = t_target.state.value[0].upper()
            label = f"ID {t_target.track_id} ({state_label})"
            cv2.putText(annotated, label, (x1, max(12, y1 - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
            # Draw trajectory line
            if len(t_target.centroids) >= 2:
                pts = np.array([(int(cx), int(cy)) for cx, cy in t_target.centroids], dtype=np.int32)
                cv2.polylines(annotated, [pts], isClosed=False, color=color, thickness=2)
        return annotated

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = max(0, ceil(len(ordered) * quantile) - 1)
        return float(ordered[index])
