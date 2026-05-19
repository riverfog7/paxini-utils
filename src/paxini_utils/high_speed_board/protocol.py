"""Pure protocol helpers for high speed board request frames."""

from paxini_utils.high_speed_board.constants import (
    BYTEORDER,
    FUNC_READ,
    FUNC_WRITE,
    LRC_MASK,
    MAX_READ_LENGTH,
    MAX_REGISTER,
    MAX_WRITE_LENGTH,
    MIN_READ_LENGTH,
    MIN_REGISTER,
    MIN_WRITE_LENGTH,
    REQUEST_HEADER,
    RESERVED_BYTE,
)
from paxini_utils.high_speed_board.errors import ProtocolError


def calculate_lrc(data: bytes) -> int:
    """Calculate the protocol LRC byte for a frame body."""
    lrc_sum = sum(data) & LRC_MASK
    return ((~lrc_sum) + 1) & LRC_MASK


def build_read_request(register: int, length: int) -> bytes:
    """Build a register read request frame."""
    _validate_register(register)
    _validate_read_length(length)
    return _build_request(FUNC_READ, register, length)


def build_write_request(register: int, data: bytes) -> bytes:
    """Build a register write request frame."""
    _validate_register(register)
    _validate_write_data(data)
    return _build_request(FUNC_WRITE, register, len(data), data)


def _build_request(function_code: int, register: int, length: int, data: bytes = b"") -> bytes:
    frame_body = b"".join(
        (
            REQUEST_HEADER,
            bytes([RESERVED_BYTE]),
            bytes([function_code]),
            register.to_bytes(2, BYTEORDER),
            length.to_bytes(2, BYTEORDER),
            data,
        )
    )
    return frame_body + bytes([calculate_lrc(frame_body)])


def _validate_register(register: int) -> None:
    if not MIN_REGISTER <= register <= MAX_REGISTER:
        raise ProtocolError(f"Register out of range: 0x{register:X}")


def _validate_read_length(length: int) -> None:
    if not MIN_READ_LENGTH <= length <= MAX_READ_LENGTH:
        raise ProtocolError(f"Read length out of range: {length}")


def _validate_write_data(data: bytes) -> None:
    if not isinstance(data, bytes):
        raise ProtocolError("Write data must be bytes")
    if not MIN_WRITE_LENGTH <= len(data) <= MAX_WRITE_LENGTH:
        raise ProtocolError(f"Write length out of range: {len(data)}")
