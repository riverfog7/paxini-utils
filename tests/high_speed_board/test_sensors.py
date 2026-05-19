import pytest

from paxini_utils.high_speed_board.constants import (
    INDEX_TIP,
    PALM_8,
    SENSOR_ORDER,
    THUMB_NEAR,
)
from paxini_utils.high_speed_board.errors import ProtocolError
from paxini_utils.high_speed_board.sensors import (
    get_distribution_range,
    get_parse_point_limit,
    get_point_count_register,
    is_palm_sensor,
    parse_connected_sensors,
    sensor_from_distribution_address,
)


def test_sensor_order_has_all_modules() -> None:
    assert len(SENSOR_ORDER) == 28
    assert SENSOR_ORDER[0] == THUMB_NEAR
    assert SENSOR_ORDER[-1] == PALM_8


def test_parse_connected_sensors_in_wire_order() -> None:
    connected = parse_connected_sensors(
        {
            0x0010: 0b1000_0001,
            0x0011: 0b0001_0000,
            0x0012: 0,
            0x0013: 0b0000_1000,
        }
    )

    assert connected == ("thumb_near", "index_nail", "ring_near", "palm_8")


def test_parse_connected_sensors_rejects_non_byte_status() -> None:
    with pytest.raises(ProtocolError):
        parse_connected_sensors({0x0010: 0x100})


def test_distribution_range_lookup() -> None:
    assert get_distribution_range(INDEX_TIP) == (0x1C00, 0x1DFF)
    assert sensor_from_distribution_address(0x1C7F) == INDEX_TIP
    assert sensor_from_distribution_address(0x4000) is None


def test_point_count_register_lookup() -> None:
    assert get_point_count_register(INDEX_TIP) == 0x003C
    assert get_point_count_register(PALM_8) == 0x0074


def test_palm_point_limit() -> None:
    assert is_palm_sensor(PALM_8)
    assert get_parse_point_limit(PALM_8, 20) == 9
    assert get_parse_point_limit(INDEX_TIP, 20) == 20


def test_unknown_sensor_rejected() -> None:
    with pytest.raises(ProtocolError):
        get_distribution_range("unknown")


def test_negative_point_count_rejected() -> None:
    with pytest.raises(ProtocolError):
        get_parse_point_limit(INDEX_TIP, -1)
