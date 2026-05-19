import pytest

from paxini_utils.high_speed_board.errors import ChecksumError, DeviceError, ProtocolError
from paxini_utils.high_speed_board.frames import (
    parse_auto_push_frame,
    parse_response_frame,
    validate_lrc,
)
from paxini_utils.high_speed_board.protocol import calculate_lrc


def with_lrc(frame_body: bytes) -> bytes:
    return frame_body + bytes([calculate_lrc(frame_body)])


def test_validate_lrc_accepts_valid_frame() -> None:
    frame = with_lrc(bytes.fromhex("AA5500030000010042"))

    validate_lrc(frame)


def test_validate_lrc_rejects_invalid_lrc() -> None:
    frame = with_lrc(bytes.fromhex("AA5500030000010042"))[:-1] + b"\x00"

    with pytest.raises(ChecksumError):
        validate_lrc(frame)


def test_validate_lrc_rejects_too_short_frame() -> None:
    with pytest.raises(ProtocolError):
        validate_lrc(b"\x00")


def test_parse_response_frame_parses_valid_frame() -> None:
    frame = with_lrc(bytes.fromhex("AA550003341202004142"))

    response = parse_response_frame(frame)

    assert response.function_code == 0x03
    assert response.register_address == 0x1234
    assert response.data_length == 2
    assert response.data == b"AB"
    assert response.raw_frame == frame


def test_parse_response_frame_rejects_invalid_header() -> None:
    frame = with_lrc(bytes.fromhex("55AA0003341202004142"))

    with pytest.raises(ProtocolError):
        parse_response_frame(frame)


def test_parse_response_frame_rejects_short_frame() -> None:
    with pytest.raises(ProtocolError):
        parse_response_frame(b"\xAA\x55")


def test_parse_response_frame_rejects_data_length_mismatch() -> None:
    frame = with_lrc(bytes.fromhex("AA550003341203004142"))

    with pytest.raises(ProtocolError):
        parse_response_frame(frame)


def test_parse_response_frame_rejects_invalid_lrc() -> None:
    frame = with_lrc(bytes.fromhex("AA550003341202004142"))[:-1] + b"\x00"

    with pytest.raises(ChecksumError):
        parse_response_frame(frame)


def test_parse_response_frame_raises_device_error_for_error_function() -> None:
    frame = with_lrc(bytes.fromhex("AA55008334120000"))

    with pytest.raises(DeviceError) as exc_info:
        parse_response_frame(frame)

    assert exc_info.value.code == 0x03


def test_parse_auto_push_frame_parses_valid_frame() -> None:
    frame = with_lrc(bytes.fromhex("AA56000300005859"))

    auto_push = parse_auto_push_frame(frame)

    assert auto_push.frame_length == 3
    assert auto_push.error_code == 0
    assert auto_push.data == b"XY"
    assert auto_push.raw_frame == frame


def test_parse_auto_push_frame_rejects_invalid_header() -> None:
    frame = with_lrc(bytes.fromhex("AA55000300005859"))

    with pytest.raises(ProtocolError):
        parse_auto_push_frame(frame)


def test_parse_auto_push_frame_rejects_short_frame() -> None:
    with pytest.raises(ProtocolError):
        parse_auto_push_frame(b"\xAA\x56")


def test_parse_auto_push_frame_rejects_invalid_frame_length() -> None:
    frame = with_lrc(bytes.fromhex("AA5600000000"))

    with pytest.raises(ProtocolError):
        parse_auto_push_frame(frame)


def test_parse_auto_push_frame_rejects_frame_length_mismatch() -> None:
    frame = with_lrc(bytes.fromhex("AA56000400005859"))

    with pytest.raises(ProtocolError):
        parse_auto_push_frame(frame)


def test_parse_auto_push_frame_rejects_invalid_lrc() -> None:
    frame = with_lrc(bytes.fromhex("AA56000300005859"))[:-1] + b"\x00"

    with pytest.raises(ChecksumError):
        parse_auto_push_frame(frame)


def test_parse_auto_push_frame_raises_device_error_for_error_code() -> None:
    frame = with_lrc(bytes.fromhex("AA5600010007"))

    with pytest.raises(DeviceError) as exc_info:
        parse_auto_push_frame(frame)

    assert exc_info.value.code == 0x07
