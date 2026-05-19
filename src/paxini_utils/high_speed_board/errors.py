"""Exceptions raised by the high speed board package."""


class BoardError(Exception):
    """Base exception for high speed board errors."""


class ProtocolError(BoardError):
    """Raised when a frame or request violates the board protocol."""


class ChecksumError(ProtocolError):
    """Raised when an LRC checksum does not match."""


class DeviceError(BoardError):
    """Raised when the board reports an error response."""

    def __init__(self, code: int, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or f"Device returned error code 0x{code:02X}")


class TransportError(BoardError):
    """Raised for serial transport failures."""


class FrameTimeoutError(TransportError):
    """Raised when a complete frame is not received before timeout."""
