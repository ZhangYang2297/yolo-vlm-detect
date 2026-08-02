from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True)
class FramePacket:
    task_id: int
    run_id: int
    trace_id: str
    frame_index: int
    source_timestamp_ms: float
    captured_at: datetime
    frame: np.ndarray

    def __post_init__(self) -> None:
        if self.task_id <= 0 or self.run_id <= 0:
            raise ValueError("task_id and run_id must be positive")
        if not self.trace_id:
            raise ValueError("trace_id must not be empty")
        if self.frame_index < 0 or self.source_timestamp_ms < 0:
            raise ValueError("frame index and timestamp must not be negative")
        if (
            not isinstance(self.frame, np.ndarray)
            or self.frame.size == 0
            or self.frame.ndim != 3
            or self.frame.shape[2] != 3
        ):
            raise ValueError("frame must be a non-empty HxWx3 BGR image")
