"""Pure payload parsing helpers for high speed board force data."""

from collections.abc import Mapping

from paxini_utils.high_speed_board.constants import (
    DISTRIBUTION_POINT_BYTES,
    DISTRIBUTION_X_OFFSET,
    DISTRIBUTION_Y_OFFSET,
    DISTRIBUTION_Z_OFFSET,
    FORCE_SCALE,
    FORCE_X_OFFSET,
    FORCE_Y_OFFSET,
    FORCE_Z_OFFSET,
    MODULE_COUNT,
    MODULE_FORCE_BYTES,
    MODULE_FORCE_LENGTH,
    SENSOR_ORDER,
    SIGNED_BYTE_LIMIT,
    SIGNED_BYTE_WRAP,
    TOTAL_FORCE_BYTES,
)
from paxini_utils.high_speed_board.errors import ProtocolError
from paxini_utils.high_speed_board.models import (
    DistributionPoint,
    Force3D,
    ModuleForce,
    SensorReading,
)
from paxini_utils.high_speed_board.sensors import get_parse_point_limit


def parse_total_force(data: bytes) -> Force3D:
    """Parse one 6-byte total-force block."""
    _validate_exact_length(data, TOTAL_FORCE_BYTES, "Total force")
    return _parse_force(
        data,
        FORCE_X_OFFSET,
        FORCE_Y_OFFSET,
        FORCE_Z_OFFSET,
        TOTAL_FORCE_BYTES,
    )


def parse_distribution_points(data: bytes) -> tuple[DistributionPoint, ...]:
    """Parse zero or more 3-byte distribution-force points."""
    _validate_bytes(data, "Distribution data")
    if len(data) % DISTRIBUTION_POINT_BYTES != 0:
        raise ProtocolError(
            f"Distribution data length must be divisible by {DISTRIBUTION_POINT_BYTES}: {len(data)}"
        )

    points: list[DistributionPoint] = []
    for index, offset in enumerate(range(0, len(data), DISTRIBUTION_POINT_BYTES)):
        raw_bytes = data[offset : offset + DISTRIBUTION_POINT_BYTES]
        points.append(
            DistributionPoint(
                index=index,
                force=_parse_force(
                    raw_bytes,
                    DISTRIBUTION_X_OFFSET,
                    DISTRIBUTION_Y_OFFSET,
                    DISTRIBUTION_Z_OFFSET,
                    DISTRIBUTION_POINT_BYTES,
                ),
                raw_bytes=raw_bytes,
            )
        )
    return tuple(points)


def parse_module_forces(data: bytes) -> tuple[ModuleForce, ...]:
    """Parse all module total-force blocks in sensor wire order."""
    _validate_exact_length(data, MODULE_FORCE_LENGTH, "Module force")

    forces: list[ModuleForce] = []
    for index in range(MODULE_COUNT):
        offset = index * MODULE_FORCE_BYTES
        raw_bytes = data[offset : offset + MODULE_FORCE_BYTES]
        forces.append(
            ModuleForce(
                sensor=SENSOR_ORDER[index],
                force=parse_total_force(raw_bytes),
            )
        )
    return tuple(forces)


def parse_sensor_reading(
    sensor: str,
    total_force_data: bytes,
    distribution_data: bytes,
) -> SensorReading:
    """Parse one sensor's total force and distribution-force data."""
    get_parse_point_limit(sensor, 0)
    return SensorReading(
        sensor=sensor,
        total_force=parse_total_force(total_force_data),
        distribution=parse_distribution_points(distribution_data),
    )


def parse_auto_push_readings(
    data: bytes,
    connected_sensors: tuple[str, ...],
    point_counts: Mapping[str, int],
) -> tuple[SensorReading, ...]:
    """Parse strict auto-push payload data into sensor readings."""
    _validate_bytes(data, "Auto-push data")
    readings: list[SensorReading] = []
    offset = 0

    for sensor in connected_sensors:
        if sensor not in point_counts:
            raise ProtocolError(f"Missing point count for sensor: {sensor}")
        point_count = get_parse_point_limit(sensor, point_counts[sensor])
        distribution_length = point_count * DISTRIBUTION_POINT_BYTES
        reading_length = TOTAL_FORCE_BYTES + distribution_length
        end = offset + reading_length
        if end > len(data):
            raise ProtocolError(
                f"Auto-push payload ended while parsing {sensor}: needed {reading_length} bytes"
            )

        readings.append(
            parse_sensor_reading(
                sensor,
                data[offset : offset + TOTAL_FORCE_BYTES],
                data[offset + TOTAL_FORCE_BYTES : end],
            )
        )
        offset = end

    if offset != len(data):
        raise ProtocolError(
            f"Auto-push payload has {len(data) - offset} trailing bytes after sensor readings"
        )
    return tuple(readings)


def _parse_force(
    data: bytes,
    x_offset: int,
    y_offset: int,
    z_offset: int,
    expected_length: int,
) -> Force3D:
    _validate_exact_length(data, expected_length, "Force")
    raw_x = _signed_byte(data[x_offset])
    raw_y = _signed_byte(data[y_offset])
    raw_z = data[z_offset]
    return Force3D(
        x=raw_x * FORCE_SCALE,
        y=raw_y * FORCE_SCALE,
        z=raw_z * FORCE_SCALE,
        raw_x=raw_x,
        raw_y=raw_y,
        raw_z=raw_z,
        raw_bytes=data,
    )


def _signed_byte(value: int) -> int:
    return value - SIGNED_BYTE_WRAP if value > SIGNED_BYTE_LIMIT else value


def _validate_exact_length(data: bytes, expected_length: int, label: str) -> None:
    _validate_bytes(data, label)
    if len(data) != expected_length:
        raise ProtocolError(f"{label} length must be {expected_length} bytes: {len(data)}")


def _validate_bytes(data: bytes, label: str) -> None:
    if not isinstance(data, bytes):
        raise ProtocolError(f"{label} must be bytes")
