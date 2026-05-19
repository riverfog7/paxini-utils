"""High-level synchronous client for the high speed communication board."""

from collections.abc import Iterable, Iterator, Mapping
from typing import Literal

from paxini_utils.high_speed_board.constants import (
    AUTO_PUSH_REGISTER,
    BYTEORDER,
    DEFAULT_BAUDRATE,
    DEFAULT_CALIBRATION_FRAME,
    DEFAULT_TIMEOUT,
    MODULE_FORCE_REGISTER,
    MODULE_FORCE_LENGTH,
    SENSOR_ORDER,
    SENSOR_STATUS_REGISTERS,
    SYSTEM_RESET_REGISTER,
    VERSION_LENGTH,
    VERSION_REGISTER,
)
from paxini_utils.high_speed_board.errors import FrameTimeoutError, ProtocolError
from paxini_utils.high_speed_board.models import AutoPushFrame, BoardStatus, ResponseFrame, SensorReading
from paxini_utils.high_speed_board.parsing import (
    parse_auto_push_readings,
    parse_distribution_points,
    parse_module_forces,
)
from paxini_utils.high_speed_board.protocol import build_read_request, build_write_request
from paxini_utils.high_speed_board.sensors import (
    get_distribution_range,
    get_parse_point_limit,
    get_point_count_register,
    parse_connected_sensors,
)
from paxini_utils.high_speed_board.state import BoardState
from paxini_utils.high_speed_board.streaming import (
    ErrorCallback,
    FrameCallback,
    ReadingCallback,
    ReadingsCallback,
    StreamingHandle,
)
from paxini_utils.high_speed_board.transport import SerialTransport

ExpectedFrame = Literal["response", "auto", "frame", None]


class HighSpeedBoard:
    """Synchronous high-level API for board commands and sensor reads."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        transport: SerialTransport | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.transport = transport or SerialTransport(port, baudrate=baudrate, timeout=timeout)
        self.state = BoardState()
        self._connected_sensors: tuple[str, ...] | None = None
        self._point_counts: dict[str, int] = {}

    def __enter__(self) -> "HighSpeedBoard":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        """Return whether the underlying transport is open."""
        return self.transport.is_open

    def open(self) -> None:
        """Open the underlying serial transport."""
        self.transport.open()

    def close(self) -> None:
        """Close the underlying serial transport."""
        self.transport.close()

    def read_register(self, register: int, length: int) -> bytes:
        """Read raw bytes from a board register."""
        self.transport.write(build_read_request(register, length))
        response = self.transport.read_response()
        self._validate_response_register(response, register)
        return response.data

    def write_register(self, register: int, data: bytes) -> ResponseFrame:
        """Write raw bytes to a board register and return the response frame."""
        self.transport.write(build_write_request(register, data))
        response = self.transport.read_response()
        self._validate_response_register(response, register)
        return response

    def send_raw_frame(
        self,
        frame: bytes,
        expected: ExpectedFrame = "response",
    ) -> ResponseFrame | AutoPushFrame | None:
        """Send a prebuilt frame and optionally read the expected response type."""
        self.transport.write(frame)
        if expected is None:
            return None
        if expected == "response":
            return self.transport.read_response()
        if expected == "auto":
            return self.transport.read_auto_push()
        if expected == "frame":
            return self.transport.read_frame()
        raise ProtocolError(f"Unknown expected frame type: {expected}")

    def get_version(self) -> str:
        """Read and decode the board firmware/version string."""
        data = self.read_register(VERSION_REGISTER, VERSION_LENGTH)
        return data.rstrip(b"\x00").decode("ascii", errors="replace")

    def enable_auto_push(self) -> ResponseFrame:
        """Enable automatic push frames on the board."""
        return self.write_register(AUTO_PUSH_REGISTER, b"\x01")

    def disable_auto_push(self, timeout: float | None = None) -> ResponseFrame | None:
        """Disable automatic push frames, tolerating no response like the reference implementation."""
        self.transport.write(build_write_request(AUTO_PUSH_REGISTER, b"\x00"))
        try:
            response = self.transport.read_response(timeout)
        except FrameTimeoutError:
            return None
        self._validate_response_register(response, AUTO_PUSH_REGISTER)
        return response

    def calibrate(self, frame: bytes | None = None) -> ResponseFrame:
        """Send a calibration frame and return the board response."""
        response = self.send_raw_frame(frame or DEFAULT_CALIBRATION_FRAME, expected="response")
        if not isinstance(response, ResponseFrame):
            raise ProtocolError("Calibration did not return a response frame")
        return response

    def reset(self, timeout: float | None = None) -> ResponseFrame | None:
        """Request a board reset, tolerating no response after the command is written."""
        self.transport.write(build_write_request(SYSTEM_RESET_REGISTER, b"\x01"))
        try:
            response = self.transport.read_response(timeout)
        except FrameTimeoutError:
            return None
        self._validate_response_register(response, SYSTEM_RESET_REGISTER)
        return response

    def get_connected_sensors(self) -> BoardStatus:
        """Read status registers and return connected sensors in wire order."""
        status_by_register = {
            register: self._read_one_byte_register(register) for register in SENSOR_STATUS_REGISTERS
        }
        connected = parse_connected_sensors(status_by_register)
        self._connected_sensors = connected
        return BoardStatus(connected_sensors=connected)

    def get_distribution_point_counts(
        self,
        sensors: Iterable[str] | None = None,
    ) -> dict[str, int]:
        """Read distribution point counts for sensors."""
        selected_sensors = tuple(sensors) if sensors is not None else self._get_or_refresh_connected_sensors()
        counts: dict[str, int] = {}
        for sensor in selected_sensors:
            register = get_point_count_register(sensor)
            data = self.read_register(register, 2)
            if len(data) != 2:
                raise ProtocolError(f"Point count register 0x{register:04X} returned {len(data)} bytes")
            count = int.from_bytes(data, BYTEORDER)
            get_parse_point_limit(sensor, count)
            counts[sensor] = count

        self._point_counts.update(counts)
        return counts

    def read_module_forces(self, update_state: bool = True) -> tuple:
        """Read total force for all modules."""
        module_forces = parse_module_forces(self.read_register(MODULE_FORCE_REGISTER, MODULE_FORCE_LENGTH))
        if update_state:
            self.state.update_module_forces(module_forces)
        return module_forces

    def read_distribution_force(
        self,
        sensor: str,
        refresh_point_count: bool = True,
        update_state: bool = True,
    ) -> SensorReading:
        """Read total force and distribution-force points for one sensor."""
        count = self._get_point_count(sensor, refresh_point_count)
        point_limit = get_parse_point_limit(sensor, count)
        module_force = self._module_force_by_sensor(sensor)
        distribution_data = self._read_distribution_data(sensor, point_limit)
        reading = SensorReading(
            sensor=sensor,
            total_force=module_force.force,
            distribution=parse_distribution_points(distribution_data),
        )
        if update_state:
            self.state.update_readings((reading,))
        return reading

    def read_connected_distribution_forces(
        self,
        refresh_status: bool = True,
        refresh_point_counts: bool = True,
        update_state: bool = True,
    ) -> tuple[SensorReading, ...]:
        """Read total force and distribution-force points for all connected sensors."""
        connected = (
            self.get_connected_sensors().connected_sensors
            if refresh_status
            else self._get_or_refresh_connected_sensors()
        )
        if refresh_point_counts or any(sensor not in self._point_counts for sensor in connected):
            self.get_distribution_point_counts(connected)

        module_forces_tuple = self.read_module_forces(update_state=update_state)
        module_forces = {module.sensor: module.force for module in module_forces_tuple}
        readings: list[SensorReading] = []
        for sensor in connected:
            point_limit = get_parse_point_limit(sensor, self._point_counts[sensor])
            readings.append(
                SensorReading(
                    sensor=sensor,
                    total_force=module_forces[sensor],
                    distribution=parse_distribution_points(
                        self._read_distribution_data(sensor, point_limit)
                    ),
                )
            )
        parsed = tuple(readings)
        if update_state:
            self.state.update_readings(parsed)
        return parsed

    def read_auto_push_frame(self, timeout: float | None = None) -> AutoPushFrame:
        """Read one raw auto-push frame."""
        return self.transport.read_auto_push(timeout)

    def read_auto_push_readings(
        self,
        timeout: float | None = None,
        connected_sensors: tuple[str, ...] | None = None,
        point_counts: Mapping[str, int] | None = None,
        update_state: bool = True,
    ) -> tuple[SensorReading, ...]:
        """Read and parse one auto-push payload into sensor readings."""
        selected_sensors = connected_sensors or self._get_or_refresh_connected_sensors()
        selected_counts = dict(point_counts or self._ensure_point_counts(selected_sensors))
        frame = self.read_auto_push_frame(timeout)
        return self._parse_auto_push_frame_readings(
            frame,
            selected_sensors,
            selected_counts,
            update_state=update_state,
        )

    def iter_auto_push_frames(self, timeout: float | None = None) -> Iterator[AutoPushFrame]:
        """Yield auto-push frames forever until transport/parsing raises."""
        while True:
            yield self.read_auto_push_frame(timeout)

    def iter_auto_push_readings(
        self,
        timeout: float | None = None,
        update_state: bool = True,
    ) -> Iterator[tuple[SensorReading, ...]]:
        """Yield parsed auto-push readings forever until transport/parsing raises."""
        while True:
            yield self.read_auto_push_readings(timeout, update_state=update_state)

    def start_streaming(
        self,
        update_state: bool = True,
        timeout: float | None = None,
        on_frame: FrameCallback | None = None,
        on_readings: ReadingsCallback | None = None,
        on_reading: ReadingCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> StreamingHandle:
        """Start background auto-push streaming with optional callbacks."""
        selected_sensors = self._get_or_refresh_connected_sensors()
        selected_counts = dict(self._ensure_point_counts(selected_sensors))

        def read_once() -> tuple[AutoPushFrame, tuple[SensorReading, ...]]:
            frame = self.read_auto_push_frame(timeout)
            readings = self._parse_auto_push_frame_readings(
                frame,
                selected_sensors,
                selected_counts,
                update_state=update_state,
            )
            return frame, readings

        return StreamingHandle(
            read_once=read_once,
            on_frame=on_frame,
            on_readings=on_readings,
            on_reading=on_reading,
            on_error=on_error,
        ).start()

    def _read_one_byte_register(self, register: int) -> int:
        data = self.read_register(register, 1)
        if len(data) != 1:
            raise ProtocolError(f"Register 0x{register:04X} returned {len(data)} bytes")
        return data[0]

    def _get_or_refresh_connected_sensors(self) -> tuple[str, ...]:
        if self._connected_sensors is None:
            return self.get_connected_sensors().connected_sensors
        return self._connected_sensors

    def _ensure_point_counts(self, sensors: tuple[str, ...]) -> Mapping[str, int]:
        missing = tuple(sensor for sensor in sensors if sensor not in self._point_counts)
        if missing:
            self.get_distribution_point_counts(sensors)
        return {sensor: self._point_counts[sensor] for sensor in sensors}

    def _get_point_count(self, sensor: str, refresh: bool) -> int:
        if refresh or sensor not in self._point_counts:
            self.get_distribution_point_counts((sensor,))
        return self._point_counts[sensor]

    def _read_distribution_data(self, sensor: str, point_count: int) -> bytes:
        start, _ = get_distribution_range(sensor)
        return self.read_register(start, point_count * 3) if point_count else b""

    def _module_force_by_sensor(self, sensor: str):
        get_distribution_range(sensor)
        for module_force in self.read_module_forces(update_state=True):
            if module_force.sensor == sensor:
                return module_force
        raise ProtocolError(f"No module force found for sensor: {sensor}")

    def _parse_auto_push_frame_readings(
        self,
        frame: AutoPushFrame,
        connected_sensors: tuple[str, ...],
        point_counts: Mapping[str, int],
        update_state: bool,
    ) -> tuple[SensorReading, ...]:
        readings = parse_auto_push_readings(frame.data, connected_sensors, point_counts)
        if update_state:
            self.state.update_readings(readings)
        return readings

    @staticmethod
    def _validate_response_register(response: ResponseFrame, register: int) -> None:
        if response.register_address != register:
            raise ProtocolError(
                f"Response register mismatch: expected 0x{register:04X}, "
                f"got 0x{response.register_address:04X}"
            )
