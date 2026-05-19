"""Sensor lookup helpers for the high speed board."""

from collections.abc import Iterable, Mapping

from paxini_utils.high_speed_board.constants import (
    DISTRIBUTION_ADDRESS_RANGES,
    MAX_STATUS_BYTE,
    MIN_POINT_COUNT,
    MIN_STATUS_BYTE,
    PALM_POINT_LIMIT,
    PALM_SENSOR_PREFIX,
    POINT_COUNT_REGISTERS,
    SENSOR_ORDER,
    STATUS_BIT_MASK_BASE,
    STATUS_REGISTER_SENSORS,
)
from paxini_utils.high_speed_board.errors import ProtocolError


def iter_sensors() -> Iterable[str]:
    """Return sensors in the board's wire order."""
    return iter(SENSOR_ORDER)


def is_palm_sensor(sensor: str) -> bool:
    """Return whether a sensor is one of the palm modules."""
    _validate_sensor(sensor)
    return sensor.startswith(PALM_SENSOR_PREFIX)


def get_distribution_range(sensor: str) -> tuple[int, int]:
    """Return the inclusive distribution-force register range for a sensor."""
    _validate_sensor(sensor)
    return DISTRIBUTION_ADDRESS_RANGES[sensor]


def get_point_count_register(sensor: str) -> int:
    """Return the point-count register for a sensor."""
    _validate_sensor(sensor)
    return POINT_COUNT_REGISTERS[sensor]


def get_parse_point_limit(sensor: str, reported_points: int) -> int:
    """Return how many distribution points should be parsed for a sensor."""
    if reported_points < MIN_POINT_COUNT:
        raise ProtocolError(f"Point count cannot be negative: {reported_points}")
    return min(reported_points, PALM_POINT_LIMIT) if is_palm_sensor(sensor) else reported_points


def sensor_from_distribution_address(address: int) -> str | None:
    """Return the sensor owning a distribution-force address, if any."""
    for sensor in SENSOR_ORDER:
        start, end = DISTRIBUTION_ADDRESS_RANGES[sensor]
        if start <= address <= end:
            return sensor
    return None


def parse_connected_sensors(status_by_register: Mapping[int, int]) -> tuple[str, ...]:
    """Parse status-register bytes into connected sensor IDs in wire order."""
    connected: list[str] = []
    for register, sensors in STATUS_REGISTER_SENSORS.items():
        status = status_by_register.get(register, MIN_STATUS_BYTE)
        if not MIN_STATUS_BYTE <= status <= MAX_STATUS_BYTE:
            raise ProtocolError(f"Status register 0x{register:04X} is not one byte: {status}")
        for bit, sensor in enumerate(sensors):
            if status & (STATUS_BIT_MASK_BASE << bit):
                connected.append(sensor)
    return tuple(connected)


def _validate_sensor(sensor: str) -> None:
    if sensor not in SENSOR_ORDER:
        raise ProtocolError(f"Unknown sensor: {sensor}")
