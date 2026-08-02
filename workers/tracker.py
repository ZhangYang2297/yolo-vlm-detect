from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import enum
import numpy as np
from ai.yolo_detector import FrameDetections

def compute_iou(box_a, box_b):
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

class TrackState(enum.Enum):
    TENTATIVE = 'tentative'
    CONFIRMED = 'confirmed'
    LOST = 'lost'

@dataclass(frozen=True)
class TrackedTarget:
    track_id: int
    state: TrackState
    class_id: int
    class_name: str
    confidence: float
    xyxy: tuple[float, float, float, float]
    age: int
    hit_count: int
    missed_count: int
    centroids: tuple[tuple[float, float], ...] = ()

_MAX_TRAJECTORY = 30

@dataclass
class Tracklet:
    track_id: int
    class_id: int
    class_name: str
    last_xyxy: tuple[float, float, float, float]
    centroids: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=_MAX_TRAJECTORY))
    age: int = 1
    hit_count: int = 1
    missed_count: int = 0
    confirmed: bool = False

    @property
    def state(self):
        if self.missed_count > 0:
            return TrackState.LOST
        if self.confirmed:
            return TrackState.CONFIRMED
        return TrackState.TENTATIVE

    @property
    def centroid(self):
        cx = (self.last_xyxy[0] + self.last_xyxy[2]) / 2.0
        cy = (self.last_xyxy[1] + self.last_xyxy[3]) / 2.0
        return (cx, cy)

    def hit(self, xyxy):
        self.last_xyxy = xyxy
        self.centroids.append(self.centroid)
        self.age += 1
        self.hit_count += 1
        self.missed_count = 0

    def miss(self):
        self.missed_count += 1

class IoUTracker:
    def __init__(self, iou_threshold=0.3, max_missed=5, confirmed_threshold=3):
        if not 0 < iou_threshold <= 1:
            raise ValueError('iou_threshold must be in (0, 1]')
        if max_missed < 1:
            raise ValueError('max_missed must be >= 1')
        if confirmed_threshold < 1:
            raise ValueError('confirmed_threshold must be >= 1')
        self._iou_threshold = iou_threshold
        self._max_missed = max_missed
        self._confirmed_threshold = confirmed_threshold
        self._next_id = 1
        self._tracks = {}
        self._total_created = 0

    def update(self, detections):
        if not detections.detections:
            self._miss_all()
            return ()

        active_tracks = {tid: t for tid, t in self._tracks.items() if t.missed_count <= self._max_missed}

        matched_track_ids = set()
        matched_det_indices = set()
        matched_pairs = []

        for det_idx, det in enumerate(detections.detections):
            best_track_id = None
            best_iou = self._iou_threshold
            for track_id, tracklet in active_tracks.items():
                if track_id in matched_track_ids:
                    continue
                iou = compute_iou(det.xyxy, tracklet.last_xyxy)
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id
            if best_track_id is not None:
                matched_track_ids.add(best_track_id)
                matched_det_indices.add(det_idx)
                matched_pairs.append((best_track_id, det_idx))

        for track_id, det_idx in matched_pairs:
            det = detections.detections[det_idx]
            tracklet = self._tracks[track_id]
            tracklet.hit(det.xyxy)
            if tracklet.age >= self._confirmed_threshold:
                tracklet.confirmed = True

        for track_id in active_tracks:
            if track_id not in matched_track_ids:
                self._tracks[track_id].miss()

        for track_id, tracklet in self._tracks.items():
            if track_id not in active_tracks:
                tracklet.miss()

        for det_idx, det in enumerate(detections.detections):
            if det_idx in matched_det_indices:
                continue
            tracklet = Tracklet(
                track_id=self._next_id, class_id=det.class_id,
                class_name=det.class_name, last_xyxy=det.xyxy,
            )
            tracklet.centroids.append(tracklet.centroid)
            self._tracks[self._next_id] = tracklet
            self._next_id += 1
            self._total_created += 1

        return tuple(
            TrackedTarget(
                track_id=tid, state=t.state, class_id=t.class_id,
                class_name=t.class_name, confidence=0.9, xyxy=t.last_xyxy,
                age=t.age, hit_count=t.hit_count, missed_count=t.missed_count,
                centroids=tuple(t.centroids),
            )
            for tid, t in sorted(self._tracks.items())
            if t.missed_count <= self._max_missed
        )

    def snapshot(self):
        active = [t for t in self._tracks.values() if t.missed_count <= self._max_missed]
        confirmed = [t for t in active if t.confirmed]
        tentative = [t for t in active if not t.confirmed]
        return {
            'active_tracks': len(active),
            'confirmed_tracks': len(confirmed),
            'tentative_tracks': len(tentative),
            'total_tracks_created': self._total_created,
        }

    def _miss_all(self):
        for tracklet in self._tracks.values():
            tracklet.miss()

    @property
    def tracks(self):
        return dict(self._tracks)