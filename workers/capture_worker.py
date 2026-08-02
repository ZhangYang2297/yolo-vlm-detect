from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from time import sleep
from typing import Optional
from uuid import uuid4

from workers.contracts import FramePacket
from workers.frame_buffer import LatestFrameBuffer


@dataclass(frozen=True)
class CaptureSnapshot:
    task_id: int
    run_id: int
    status: str
    captured_frames: int
    dropped_frames: int
    reconnects: int
    last_frame_at: Optional[str]
    last_error: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


class CaptureWorker:
    def __init__(
        self,
        task_id: int,
        run_id: int,
        stream,
        output: LatestFrameBuffer,
        *,
        loop_on_eof: bool = True,
        reconnect_attempts: int = 3,
        reconnect_delay_seconds: float = 0.2,
        stop_event: Optional[Event] = None,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.stream = stream
        self.output = output
        self.loop_on_eof = loop_on_eof
        self.reconnect_attempts = max(0, reconnect_attempts)
        self.reconnect_delay_seconds = max(0.0, reconnect_delay_seconds)
        self._stop_event = stop_event or Event()
        self._lock = Lock()
        self._thread: Optional[Thread] = None
        self._status = "created"
        self._captured_frames = 0
        self._dropped_frames = 0
        self._reconnects = 0
        self._last_frame_at: Optional[str] = None
        self._last_error: Optional[str] = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self.run,
                name=f"capture-{self.task_id}-{self.run_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, timeout_seconds))
        with self._lock:
            if self._status not in {"failed", "stopped"}:
                self._status = "stopped"

    def run(self) -> None:
        self._set_status("connecting")
        try:
            if not self.stream.open():
                self._fail("Unable to open video stream")
                return
            self._set_status("running")
            reconnect_failures = 0
            while not self._stop_event.is_set():
                try:
                    result = self.stream.read()
                except StopIteration:
                    result = None
                if result is None or not result.ok:
                    is_eof = bool(result is not None and result.eof)
                    if is_eof and not self.loop_on_eof:
                        break
                    if reconnect_failures >= self.reconnect_attempts:
                        self._fail("Video stream read failed after reconnect attempts")
                        return
                    reconnect_failures += 1
                    if self.reconnect_delay_seconds:
                        sleep(self.reconnect_delay_seconds)
                    if not self.stream.restart():
                        continue
                    with self._lock:
                        self._reconnects += 1
                    continue

                reconnect_failures = 0
                captured_at = datetime.now(timezone.utc)
                packet = FramePacket(
                    task_id=self.task_id,
                    run_id=self.run_id,
                    trace_id=str(uuid4()),
                    frame_index=result.frame_index,
                    source_timestamp_ms=result.timestamp_ms,
                    captured_at=captured_at,
                    frame=result.frame,
                )
                dropped = self.output.put(packet)
                with self._lock:
                    self._captured_frames += 1
                    self._dropped_frames += dropped
                    self._last_frame_at = captured_at.isoformat()
                frame_interval = float(
                    getattr(self.stream, "frame_interval_seconds", 0.0)
                )
                if frame_interval > 0 and self._stop_event.wait(frame_interval):
                    break
            self._set_status("stopped")
        except Exception as exc:
            self._fail(str(exc))
        finally:
            self.stream.release()

    def snapshot(self) -> CaptureSnapshot:
        with self._lock:
            return CaptureSnapshot(
                task_id=self.task_id,
                run_id=self.run_id,
                status=self._status,
                captured_frames=self._captured_frames,
                dropped_frames=self._dropped_frames,
                reconnects=self._reconnects,
                last_frame_at=self._last_frame_at,
                last_error=self._last_error,
            )

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._status = status

    def _fail(self, message: str) -> None:
        with self._lock:
            self._status = "failed"
            self._last_error = message
