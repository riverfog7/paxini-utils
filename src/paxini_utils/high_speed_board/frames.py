"""Pure frame parsing helpers for high speed board responses."""

from paxini_utils.high_speed_board.constants import (
    AUTO_PUSH_DATA_OFFSET,
    AUTO_PUSH_ERROR_CODE_OFFSET,
    AUTO_PUSH_FRAME_LENGTH_OFFSET,
    AUTO_PUSH_HEADER,
    AUTO_PUSH_MIN_FRAME_LENGTH,
    BYTEORDER,
    DEVICE_ERROR_CODE_MASK,
    DEVICE_ERROR_FUNCTION_MASK,
    ERROR_CODE_LENGTH,
    LRC_LENGTH,
    RESPONSE_DATA_LENGTH_OFFSET,
    RESPONSE_DATA_OFFSET,
    RESPONSE_FUNCTION_OFFSET,
    RESPONSE_HEADER,
    RESPONSE_MIN_FRAME_LENGTH,
    RESPONSE_REGISTER_OFFSET,
)
from paxini_utils.high_speed_board.errors import ChecksumError, DeviceError, ProtocolError
from paxini_utils.high_speed_board.models import AutoPushFrame, ResponseFrame
from paxini_utils.high_speed_board.protocol import calculate_lrc


def validate_lrc(frame: bytes) -> None:
    """Validate a complete frame's trailing LRC byte."""
    if len(frame) <= LRC_LENGTH:
        raise ProtocolError("Frame is too short to contain an LRC")

    expected_lrc = calculate_lrc(frame[:-LRC_LENGTH])
    actual_lrc = frame[-LRC_LENGTH]
    if actual_lrc != expected_lrc:
        raise ChecksumError(
            f"Invalid LRC: expected 0x{expected_lrc:02X}, got 0x{actual_lrc:02X}"
        )


def parse_response_frame(frame: bytes) -> ResponseFrame:
    """Parse a complete AA55 response frame."""
    if len(frame) < RESPONSE_MIN_FRAME_LENGTH:
        raise ProtocolError(f"Response frame is too short: {len(frame)} bytes")
    if not frame.startswith(RESPONSE_HEADER):
        raise ProtocolError("Invalid response frame header")

    validate_lrc(frame)

    function_code = frame[RESPONSE_FUNCTION_OFFSET]
    register_address = int.from_bytes(
        frame[RESPONSE_REGISTER_OFFSET:RESPONSE_DATA_LENGTH_OFFSET], BYTEORDER
    )
    data_length = int.from_bytes(
        frame[RESPONSE_DATA_LENGTH_OFFSET:RESPONSE_DATA_OFFSET], BYTEORDER
    )
    expected_length = RESPONSE_DATA_OFFSET + data_length + LRC_LENGTH
    if len(frame) != expected_length:
        raise ProtocolError(
            f"Response frame length mismatch: expected {expected_length} bytes, got {len(frame)}"
        )

    if function_code & DEVICE_ERROR_FUNCTION_MASK:
        raise DeviceError(function_code & DEVICE_ERROR_CODE_MASK)

    data = frame[RESPONSE_DATA_OFFSET:-LRC_LENGTH]
    return ResponseFrame(
        function_code=function_code,
        register_address=register_address,
        data_length=data_length,
        data=data,
        raw_frame=frame,
    )


def parse_auto_push_frame(frame: bytes) -> AutoPushFrame:
    """Parse a complete AA56 automatic push frame."""
    if len(frame) < AUTO_PUSH_MIN_FRAME_LENGTH:
        raise ProtocolError(f"Auto-push frame is too short: {len(frame)} bytes")
    if not frame.startswith(AUTO_PUSH_HEADER):
        raise ProtocolError("Invalid auto-push frame header")

    validate_lrc(frame)

    frame_length = int.from_bytes(
        frame[AUTO_PUSH_FRAME_LENGTH_OFFSET:AUTO_PUSH_ERROR_CODE_OFFSET], BYTEORDER
    )
    if frame_length < ERROR_CODE_LENGTH:
        raise ProtocolError(f"Invalid auto-push frame length: {frame_length}")

    data_length = frame_length - ERROR_CODE_LENGTH
    expected_length = AUTO_PUSH_DATA_OFFSET + data_length + LRC_LENGTH
    if len(frame) != expected_length:
        raise ProtocolError(
            f"Auto-push frame length mismatch: expected {expected_length} bytes, got {len(frame)}"
        )

    error_code = frame[AUTO_PUSH_ERROR_CODE_OFFSET]
    if error_code != 0:
        raise DeviceError(error_code)

    data = frame[AUTO_PUSH_DATA_OFFSET:-LRC_LENGTH]
    return AutoPushFrame(
        frame_length=frame_length,
        error_code=error_code,
        data=data,
        raw_frame=frame,
    )
