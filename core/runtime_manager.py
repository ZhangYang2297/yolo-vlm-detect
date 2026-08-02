from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

from config.settings import PROJECT_ROOT
from ai.yolo_detector import UltralyticsBackend, YoloDetector
from core.stream_client import OpenCVStreamClient
from workers.capture_worker import CaptureWorker
from workers.frame_buffer import LatestFrameBuffer
from workers.inference_worker import InferenceWorker


@dataclass
class RuntimeSession:
    worker: CaptureWorker
    buffer: LatestFrameBuffer


class RuntimeManager:
    def __init__(
        self,
        *,
        stream_factory: Callable = OpenCVStreamClient,
        buffer_capacity: int = 4,
        inference_worker: Optional[InferenceWorker] = None,
        detector_factory: Optional[Callable] = None,
    ) -> None:
        self._stream_factory = stream_factory
        self._buffer_capacity = buffer_capacity
        self._sessions: dict[int, RuntimeSession] = {}
        self._lock = Lock()
        self._inference_worker = inference_worker or InferenceWorker(
            detector_factory=detector_factory or self._create_default_detector
        )

    def start(self, task, run) -> dict:
        source = self._resolve_source(task.source_url)
        self._inference_worker.start()
        with self._lock:
            existing = self._sessions.get(task.id)
            if existing is not None:
                snapshot = existing.worker.snapshot()
                if snapshot.run_id == run.id and snapshot.status in {
                    "created", "connecting", "running"
                }:
                    return self._session_status(existing)
                existing.worker.stop()
                self._inference_worker.unregister(task.id)
                existing.buffer.clear()
            buffer = LatestFrameBuffer(self._buffer_capacity)
            worker = CaptureWorker(
                task_id=task.id,
                run_id=run.id,
                stream=self._stream_factory(source),
                output=buffer,
                loop_on_eof=task.source_type in {"video", "local_file"},
            )
            session = RuntimeSession(worker=worker, buffer=buffer)
            self._sessions[task.id] = session
            self._inference_worker.register(task.id, buffer)
            worker.start()
            return self._session_status(session)

    def stop(self, task_id: int) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            return None
        session.worker.stop()
        self._inference_worker.unregister(task_id)
        session.buffer.clear()
        return self._session_status(session)

    def status(self, task_id: int) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            return None
        return self._session_status(session)

    def latest_frame(self, task_id: int):
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            return None
        return session.buffer.peek_latest()

    def latest_detection(self, task_id: int):
        return self._inference_worker.latest_result(task_id)

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.worker.stop()
            session.buffer.clear()
        self._inference_worker.stop()

    def _session_status(self, session: RuntimeSession) -> dict:
        status = session.worker.snapshot().to_dict()
        status["buffer_size"] = session.buffer.size
        status["inference"] = self._inference_worker.task_snapshot(
            status["task_id"]
        )
        status["tracker"] = self._inference_worker.tracker_snapshot(
            status["task_id"]
        )
        status["candidate"] = self._inference_worker.producer_snapshot(
            status["task_id"]
        )
        return status

    @staticmethod
    def _create_default_detector():
        from config.settings import get_settings

        config = get_settings().yolo
        model_path = Path(config.model)
        if not model_path.is_absolute():
            model_path = PROJECT_ROOT / model_path
        backend = UltralyticsBackend.from_model_path(str(model_path))
        return YoloDetector(
            backend=backend,
            model_name=model_path.name,
            device=config.device,
            half=config.half,
            confidence=config.confidence,
            iou_threshold=config.iou_threshold,
            image_size=config.image_size,
        )

    @staticmethod
    def _resolve_source(source):
        if not isinstance(source, str):
            return source
        candidate = Path(source)
        if candidate.is_absolute() or "://" in source:
            return source
        resolved = (PROJECT_ROOT / candidate).resolve()
        return str(resolved)
