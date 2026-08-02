from collections import deque
from threading import Lock
from typing import Optional

from workers.contracts import FramePacket


class LatestFrameBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items: deque[FramePacket] = deque()
        self._dropped_frames = 0
        self._lock = Lock()

    def put(self, packet: FramePacket) -> int:
        dropped = 0
        with self._lock:
            if len(self._items) >= self._capacity:
                self._items.popleft()
                self._dropped_frames += 1
                dropped = 1
            self._items.append(packet)
        return dropped

    def get(self) -> Optional[FramePacket]:
        with self._lock:
            if not self._items:
                return None
            return self._items.popleft()

    def get_latest(self) -> tuple[Optional[FramePacket], int]:
        with self._lock:
            if not self._items:
                return None, 0
            latest = self._items[-1]
            discarded = len(self._items) - 1
            self._items.clear()
            self._dropped_frames += discarded
            return latest, discarded

    def peek_latest(self) -> Optional[FramePacket]:
        with self._lock:
            if not self._items:
                return None
            return self._items[-1]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def dropped_frames(self) -> int:
        with self._lock:
            return self._dropped_frames
