"""Background auto-push streaming helpers."""

from collections.abc import Callable
from threading import Event, Thread

from paxini_utils.high_speed_board.models import AutoPushFrame, SensorReading

StreamRead = Callable[[], tuple[AutoPushFrame, tuple[SensorReading, ...]]]
FrameCallback = Callable[[AutoPushFrame], None]
ReadingsCallback = Callable[[tuple[SensorReading, ...]], None]
ReadingCallback = Callable[[SensorReading], None]
ErrorCallback = Callable[[Exception], None]


class StreamingHandle:
    """Control handle for a background auto-push streaming thread."""

    def __init__(
        self,
        read_once: StreamRead,
        on_frame: FrameCallback | None = None,
        on_readings: ReadingsCallback | None = None,
        on_reading: ReadingCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._read_once = read_once
        self._on_frame = on_frame
        self._on_readings = on_readings
        self._on_reading = on_reading
        self._on_error = on_error
        self._stop_event = Event()
        self._thread = Thread(target=self._run, daemon=True)
        self.last_error: Exception | None = None

    @property
    def is_running(self) -> bool:
        """Return whether the streaming thread is alive."""
        return self._thread.is_alive()

    def start(self) -> "StreamingHandle":
        """Start streaming in the background."""
        self._thread.start()
        return self

    def stop(self) -> None:
        """Request the streaming thread to stop."""
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the streaming thread to exit."""
        self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame, readings = self._read_once()
                if self._on_frame is not None:
                    self._on_frame(frame)
                if self._on_readings is not None:
                    self._on_readings(readings)
                if self._on_reading is not None:
                    for reading in readings:
                        self._on_reading(reading)
            except Exception as exc:
                self.last_error = exc
                if self._on_error is not None:
                    self._on_error(exc)
