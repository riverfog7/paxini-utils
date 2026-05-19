import pytest

from paxini_utils.high_speed_board.constants import (
    INDEX_TIP,
    MODULE_FORCE_BYTES,
    MODULE_FORCE_LENGTH,
    PALM_8,
    SENSOR_ORDER,
    THUMB_NEAR,
)
from paxini_utils.high_speed_board.errors import ProtocolError
from paxini_utils.high_speed_board.parsing import (
    parse_auto_push_readings,
    parse_distribution_points,
    parse_module_forces,
    parse_sensor_reading,
    parse_total_force,
)


def test_parse_total_force_parses_signed_and_unsigned_axes() -> None:
    force = parse_total_force(bytes([0x7F, 0x00, 0x80, 0x00, 0xFF, 0x00]))

    assert force.raw_x == 127
    assert force.raw_y == -128
    assert force.raw_z == 255
    assert force.x == pytest.approx(12.7)
    assert force.y == pytest.approx(-12.8)
    assert force.z == pytest.approx(25.5)
    assert force.raw_bytes == bytes([0x7F, 0x00, 0x80, 0x00, 0xFF, 0x00])


@pytest.mark.parametrize("data", [b"", b"\x00" * 5, b"\x00" * 7])
def test_parse_total_force_requires_exact_length(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_total_force(data)


def test_parse_distribution_points_parses_points() -> None:
    points = parse_distribution_points(bytes([0x01, 0xFF, 0x02, 0x80, 0x7F, 0x03]))

    assert len(points) == 2
    assert points[0].index == 0
    assert points[0].force.raw_x == 1
    assert points[0].force.raw_y == -1
    assert points[0].force.raw_z == 2
    assert points[0].force.x == pytest.approx(0.1)
    assert points[0].force.y == pytest.approx(-0.1)
    assert points[0].force.z == pytest.approx(0.2)
    assert points[0].raw_bytes == bytes([0x01, 0xFF, 0x02])
    assert points[1].index == 1
    assert points[1].force.raw_x == -128
    assert points[1].force.raw_y == 127
    assert points[1].force.raw_z == 3


def test_parse_distribution_points_accepts_empty_data() -> None:
    assert parse_distribution_points(b"") == ()


def test_parse_distribution_points_rejects_invalid_length() -> None:
    with pytest.raises(ProtocolError):
        parse_distribution_points(b"\x00\x01")


def test_parse_module_forces_parses_all_modules_in_sensor_order() -> None:
    payload = b"".join(
        bytes([index, 0x00, index + 1, 0x00, index + 2, 0x00])
        for index in range(len(SENSOR_ORDER))
    )

    forces = parse_module_forces(payload)

    assert len(forces) == len(SENSOR_ORDER)
    assert forces[0].sensor == SENSOR_ORDER[0]
    assert forces[-1].sensor == SENSOR_ORDER[-1]
    assert forces[0].force.raw_x == 0
    assert forces[0].force.raw_y == 1
    assert forces[0].force.raw_z == 2
    assert forces[-1].force.raw_x == 27
    assert forces[-1].force.raw_y == 28
    assert forces[-1].force.raw_z == 29


@pytest.mark.parametrize(
    "data",
    [b"\x00" * (MODULE_FORCE_LENGTH - 1), b"\x00" * (MODULE_FORCE_LENGTH + 1)],
)
def test_parse_module_forces_requires_exact_length(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_module_forces(data)


def test_parse_sensor_reading_parses_total_force_and_distribution() -> None:
    reading = parse_sensor_reading(
        INDEX_TIP,
        bytes([0x01, 0x00, 0x02, 0x00, 0x03, 0x00]),
        bytes([0x04, 0x05, 0x06]),
    )

    assert reading.sensor == INDEX_TIP
    assert reading.total_force is not None
    assert reading.total_force.raw_x == 1
    assert len(reading.distribution) == 1
    assert reading.distribution[0].force.raw_z == 6


def test_parse_sensor_reading_rejects_unknown_sensor() -> None:
    with pytest.raises(ProtocolError):
        parse_sensor_reading("unknown", b"\x00" * 6, b"")


def test_parse_auto_push_readings_parses_connected_sensors() -> None:
    first_force = bytes([0x01, 0x00, 0x02, 0x00, 0x03, 0x00])
    first_distribution = bytes([0x04, 0x05, 0x06])
    second_force = bytes([0x07, 0x00, 0x08, 0x00, 0x09, 0x00])
    payload = first_force + first_distribution + second_force

    readings = parse_auto_push_readings(
        payload,
        (THUMB_NEAR, INDEX_TIP),
        {THUMB_NEAR: 1, INDEX_TIP: 0},
    )

    assert len(readings) == 2
    assert readings[0].sensor == THUMB_NEAR
    assert readings[0].total_force is not None
    assert readings[0].total_force.raw_x == 1
    assert len(readings[0].distribution) == 1
    assert readings[1].sensor == INDEX_TIP
    assert readings[1].total_force is not None
    assert readings[1].total_force.raw_x == 7
    assert readings[1].distribution == ()


def test_parse_auto_push_readings_caps_palm_points() -> None:
    total_force = b"\x00" * MODULE_FORCE_BYTES
    distribution = bytes(range(30))

    readings = parse_auto_push_readings(
        total_force + distribution[:27],
        (PALM_8,),
        {PALM_8: 10},
    )

    assert len(readings) == 1
    assert len(readings[0].distribution) == 9


def test_parse_auto_push_readings_rejects_trailing_bytes() -> None:
    with pytest.raises(ProtocolError):
        parse_auto_push_readings(b"\x00" * 7, (THUMB_NEAR,), {THUMB_NEAR: 0})


def test_parse_auto_push_readings_rejects_insufficient_payload() -> None:
    with pytest.raises(ProtocolError):
        parse_auto_push_readings(b"\x00" * 5, (THUMB_NEAR,), {THUMB_NEAR: 0})


def test_parse_auto_push_readings_rejects_missing_point_count() -> None:
    with pytest.raises(ProtocolError):
        parse_auto_push_readings(b"\x00" * 6, (THUMB_NEAR,), {})


def test_parse_auto_push_readings_rejects_negative_point_count() -> None:
    with pytest.raises(ProtocolError):
        parse_auto_push_readings(b"\x00" * 6, (THUMB_NEAR,), {THUMB_NEAR: -1})
