"""Serial transport for high speed board frames."""

from __future__ import annotations

import time
from types import TracebackType

from serial.serialposix import Serial

from paxini_utils.high_speed_board.constants import (
    AUTO_PUSH_DATA_OFFSET,
    AUTO_PUSH_ERROR_CODE_OFFSET,
    AUTO_PUSH_FRAME_LENGTH_OFFSET,
    AUTO_PUSH_HEADER,
    AUTO_PUSH_MIN_FRAME_LENGTH,
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT,
    ERROR_CODE_LENGTH,
    LRC_LENGTH,
    MIN_HEADER_SEARCH_LENGTH,
    RESPONSE_DATA_LENGTH_OFFSET,
    RESPONSE_DATA_OFFSET,
    RESPONSE_HEADER,
    SERIAL_BYTESIZE,
    SERIAL_PARITY,
    SERIAL_READ_CHUNK_SIZE,
    SERIAL_STOPBITS,
    BYTEORDER,
)
from paxini_utils.high_speed_board.errors import FrameTimeoutError, ProtocolError, TransportError
from paxini_utils.high_speed_board.frames import parse_auto_push_frame, parse_response_frame
from paxini_utils.high_speed_board.models import AutoPushFrame, ResponseFrame


class SerialTransport:
    """Explicit-open serial transport for complete board frames."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Serial | None = None
        self._buffer = bytearray()

    def __enter__(self) -> SerialTransport:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        """Return whether the underlying serial connection is open."""
        return self._serial is not None and bool(self._serial.is_open)

    def open(self) -> None:
        """Open the serial connection."""
        if self.is_open:
            return

        try:
            self._serial = Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=SERIAL_BYTESIZE,
                parity=SERIAL_PARITY,
                stopbits=SERIAL_STOPBITS,
            )
        except Exception as exc:
            self._serial = None
            raise TransportError(f"Failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the serial connection."""
        if self._serial is None:
            return

        try:
            self._serial.close()
        except Exception as exc:
            raise TransportError(f"Failed to close serial port {self.port}: {exc}") from exc
        finally:
            self._serial = None
            self._buffer.clear()

    def write(self, frame: bytes) -> None:
        """Write a raw request frame to the serial connection."""
        if not isinstance(frame, bytes):
            raise ProtocolError("Serial frame must be bytes")

        connection = self._require_open()
        try:
            written = connection.write(frame)
        except Exception as exc:
            raise TransportError(f"Failed to write serial frame: {exc}") from exc

        if written != len(frame):
            raise TransportError(f"Incomplete serial write: expected {len(frame)} bytes, wrote {written}")

    def read_frame(self, timeout: float | None = None) -> ResponseFrame | AutoPushFrame:
        """Read and parse the next response or auto-push frame."""
        frame = self._read_until_frame(self.timeout if timeout is None else timeout)
        if frame.startswith(RESPONSE_HEADER):
            return parse_response_frame(frame)
        if frame.startswith(AUTO_PUSH_HEADER):
            return parse_auto_push_frame(frame)
        raise ProtocolError("Unknown frame header")

    def read_response(self, timeout: float | None = None) -> ResponseFrame:
        """Read and parse the next AA55 response frame."""
        frame = self.read_frame(timeout)
        if not isinstance(frame, ResponseFrame):
            raise ProtocolError("Expected response frame, received auto-push frame")
        return frame

    def read_auto_push(self, timeout: float | None = None) -> AutoPushFrame:
        """Read and parse the next AA56 auto-push frame."""
        frame = self.read_frame(timeout)
        if not isinstance(frame, AutoPushFrame):
            raise ProtocolError("Expected auto-push frame, received response frame")
        return frame

    def _read_until_frame(self, timeout: float) -> bytes:
        connection = self._require_open()
        deadline = time.monotonic() + timeout

        while True:
            frame = self._try_extract_frame()
            if frame is not None:
                return frame

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FrameTimeoutError("Timed out waiting for a complete frame")

            try:
                connection.timeout = min(self.timeout, remaining)
                chunk = connection.read(SERIAL_READ_CHUNK_SIZE)
            except Exception as exc:
                raise TransportError(f"Failed to read serial frame: {exc}") from exc

            if chunk:
                self._buffer.extend(chunk)

    def _try_extract_frame(self) -> bytes | None:
        header_index = self._find_next_header()
        if header_index is None:
            self._drop_unusable_buffer_prefix()
            return None

        if header_index > 0:
            del self._buffer[:header_index]

        expected_length = self._expected_frame_length()
        if expected_length is None or len(self._buffer) < expected_length:
            return None

        frame = bytes(self._buffer[:expected_length])
        del self._buffer[:expected_length]
        return frame

    def _find_next_header(self) -> int | None:
        response_index = self._buffer.find(RESPONSE_HEADER)
        auto_push_index = self._buffer.find(AUTO_PUSH_HEADER)
        indexes = [index for index in (response_index, auto_push_index) if index >= 0]
        return min(indexes) if indexes else None

    def _expected_frame_length(self) -> int | None:
        if len(self._buffer) < MIN_HEADER_SEARCH_LENGTH:
            return None

        if self._buffer.startswith(RESPONSE_HEADER):
            if len(self._buffer) < RESPONSE_DATA_OFFSET:
                return None
            data_length = int.from_bytes(
                self._buffer[RESPONSE_DATA_LENGTH_OFFSET:RESPONSE_DATA_OFFSET], BYTEORDER
            )
            return RESPONSE_DATA_OFFSET + data_length + LRC_LENGTH

        if self._buffer.startswith(AUTO_PUSH_HEADER):
            if len(self._buffer) < AUTO_PUSH_ERROR_CODE_OFFSET:
                return None
            frame_length = int.from_bytes(
                self._buffer[AUTO_PUSH_FRAME_LENGTH_OFFSET:AUTO_PUSH_ERROR_CODE_OFFSET], BYTEORDER
            )
            if frame_length < ERROR_CODE_LENGTH:
                return AUTO_PUSH_MIN_FRAME_LENGTH
            data_length = frame_length - ERROR_CODE_LENGTH
            return AUTO_PUSH_DATA_OFFSET + data_length + LRC_LENGTH

        return None

    def _drop_unusable_buffer_prefix(self) -> None:
        if len(self._buffer) < MIN_HEADER_SEARCH_LENGTH:
            return
        if self._buffer[-1:] == RESPONSE_HEADER[:1]:
            del self._buffer[:-1]
            return
        self._buffer.clear()

    def _require_open(self) -> Serial:
        if self._serial is None or not self._serial.is_open:
            raise TransportError("Serial transport is not open")
        return self._serial
