import pytest

from paxini_utils.high_speed_board.constants import (
    AUTO_PUSH_REGISTER,
    KNOWN_ENABLE_AUTO_PUSH_REQUEST,
    KNOWN_VERSION_REQUEST,
    VERSION_LENGTH,
    VERSION_REGISTER,
)
from paxini_utils.high_speed_board.errors import ProtocolError
from paxini_utils.high_speed_board.protocol import (
    build_read_request,
    build_write_request,
    calculate_lrc,
)


def test_calculate_lrc_matches_known_version_request() -> None:
    frame_body = KNOWN_VERSION_REQUEST[:-1]
    assert calculate_lrc(frame_body) == KNOWN_VERSION_REQUEST[-1]


def test_build_read_request_matches_reference_frame() -> None:
    assert build_read_request(VERSION_REGISTER, VERSION_LENGTH) == KNOWN_VERSION_REQUEST


def test_build_write_request_matches_auto_push_reference_frame() -> None:
    assert build_write_request(AUTO_PUSH_REGISTER, b"\x01") == KNOWN_ENABLE_AUTO_PUSH_REQUEST


@pytest.mark.parametrize("register", [-1, 0x10000])
def test_build_read_request_rejects_invalid_register(register: int) -> None:
    with pytest.raises(ProtocolError):
        build_read_request(register, 1)


@pytest.mark.parametrize("length", [0, 513])
def test_build_read_request_rejects_invalid_length(length: int) -> None:
    with pytest.raises(ProtocolError):
        build_read_request(VERSION_REGISTER, length)


@pytest.mark.parametrize("data", [b"", bytes(range(11))])
def test_build_write_request_rejects_invalid_length(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        build_write_request(AUTO_PUSH_REGISTER, data)


def test_build_write_request_rejects_non_bytes() -> None:
    with pytest.raises(ProtocolError):
        build_write_request(AUTO_PUSH_REGISTER, "01")  # type: ignore[arg-type]
