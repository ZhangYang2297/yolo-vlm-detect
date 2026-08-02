from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from workers.roi import ROI
from workers.tracker import TrackState, TrackedTarget


@dataclass(frozen=True)
class CandidateEvent:
    event_id: str
    task_id: int
    run_id: int
    track_id: int
    roi_name: str
    trigger_reason: str
    triggered_at: datetime
    frame_index: int
    source_timestamp_ms: float


_MAX_RECENT_EVENTS = 50


class CandidateEventProducer:
    def __init__(
        self,
        rois: tuple[ROI, ...] = (),
        cooldown_seconds: float = 5.0,
        require_confirmed: bool = True,
    ) -> None:
        self._rois = rois
        self._cooldown_seconds = max(0.0, cooldown_seconds)
        self._require_confirmed = require_confirmed
        self._last_trigger: dict[int, datetime] = {}
        self._events: list[CandidateEvent] = []
        self._next_id = 1
        self._recent: deque[CandidateEvent] = deque(maxlen=_MAX_RECENT_EVENTS)

    @property
    def events(self) -> tuple[CandidateEvent, ...]:
        return tuple(self._events)

    @property
    def recent_events(self) -> tuple[CandidateEvent, ...]:
        return tuple(self._recent)

    @property
    def rois(self) -> tuple[ROI, ...]:
        return self._rois

    def update(
        self,
        task_id: int,
        run_id: int,
        tracks: tuple[TrackedTarget, ...],
        frame_index: int,
        source_timestamp_ms: float,
    ) -> tuple[CandidateEvent, ...]:
        if not self._rois or not tracks:
            return ()

        produced: list[CandidateEvent] = []
        now = datetime.now(timezone.utc)

        for track in tracks:
            if self._require_confirmed and track.state != TrackState.CONFIRMED:
                continue

            centroid = self._centroid(track.xyxy)

            for roi in self._rois:
                if not roi.contains(centroid):
                    continue

                # Check cooldown
                last = self._last_trigger.get(track.track_id)
                if last is not None:
                    elapsed = (now - last).total_seconds()
                    if elapsed < self._cooldown_seconds:
                        continue

                event = CandidateEvent(
                    event_id=f"evt-{self._next_id}",
                    task_id=task_id,
                    run_id=run_id,
                    track_id=track.track_id,
                    roi_name=roi.name,
                    trigger_reason=f"person_in_roi:{roi.name}",
                    triggered_at=now,
                    frame_index=frame_index,
                    source_timestamp_ms=source_timestamp_ms,
                )
                self._events.append(event)
                self._recent.append(event)
                self._last_trigger[track.track_id] = now
                self._next_id += 1
                produced.append(event)

        return tuple(produced)

    def snapshot(self) -> dict:
        return {
            "total_events": len(self._events),
            "recent_events": len(self._recent),
            "active_rois": len(self._rois),
            "active_track_cooldowns": len(self._last_trigger),
        }

    @staticmethod
    def _centroid(xyxy: tuple[float, float, float, float]) -> tuple[float, float]:
        cx = (xyxy[0] + xyxy[2]) / 2.0
        cy = (xyxy[1] + xyxy[3]) / 2.0
        return (cx, cy)
