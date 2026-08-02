from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np


@dataclass(frozen=True)
class StreamRead:
    ok: bool
    frame: Optional[np.ndarray] = None
    frame_index: int = 0
    timestamp_ms: float = 0.0
    eof: bool = False


class OpenCVStreamClient:
    def __init__(self, source: Union[str, int]) -> None:
        self.source = source
        self._capture: Optional[cv2.VideoCapture] = None
        self._frame_index = 0
        self._is_local_file = isinstance(source, str) and Path(source).is_file()
        self._frame_interval_seconds = 0.0

    def open(self) -> bool:
        self.release()
        self._capture = cv2.VideoCapture(self.source)
        self._frame_index = 0
        fps = float(self._capture.get(cv2.CAP_PROP_FPS)) if self._capture.isOpened() else 0.0
        self._frame_interval_seconds = 1.0 / fps if self._is_local_file and fps > 0 else 0.0
        return bool(self._capture.isOpened())

    def read(self) -> StreamRead:
        if self._capture is None or not self._capture.isOpened():
            return StreamRead(ok=False)
        ok, frame = self._capture.read()
        if not ok:
            return StreamRead(ok=False, eof=self._is_local_file)
        frame_index = self._frame_index
        self._frame_index += 1
        timestamp_ms = max(0.0, float(self._capture.get(cv2.CAP_PROP_POS_MSEC)))
        return StreamRead(
            ok=True,
            frame=frame,
            frame_index=frame_index,
            timestamp_ms=timestamp_ms,
        )

    def restart(self) -> bool:
        return self.open()

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def frame_interval_seconds(self) -> float:
        return self._frame_interval_seconds
