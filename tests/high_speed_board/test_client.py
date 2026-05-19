import pytest

from paxini_utils.high_speed_board.client import HighSpeedBoard
from paxini_utils.high_speed_board.constants import (
    AUTO_PUSH_REGISTER,
    DEFAULT_CALIBRATION_FRAME,
    INDEX_TIP,
    MODULE_FORCE_LENGTH,
    MODULE_FORCE_REGISTER,
    PALM_8,
    SENSOR_STATUS_REGISTERS,
    SYSTEM_RESET_REGISTER,
    THUMB_NEAR,
    VERSION_LENGTH,
    VERSION_REGISTER,
)
from paxini_utils.high_speed_board.errors import FrameTimeoutError, ProtocolError
from paxini_utils.high_speed_board.models import AutoPushFrame, ResponseFrame
from paxini_utils.high_speed_board.protocol import build_read_request, build_write_request
from paxini_utils.high_speed_board.sensors import get_distribution_range, get_point_count_register


class FakeTransport:
    def __init__(self, frames: list[ResponseFrame | AutoPushFrame | Exception] | None = None) -> None:
        self.frames = frames or []
        self.writes: list[bytes] = []
        self.is_open = False
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        self.open_calls += 1
        self.is_open = True

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False

    def write(self, frame: bytes) -> None:
        self.writes.append(frame)

    def read_response(self, timeout: float | None = None) -> ResponseFrame:
        frame = self._pop_frame()
        if isinstance(frame, ResponseFrame):
            return frame
        raise ProtocolError("expected response")

    def read_auto_push(self, timeout: float | None = None) -> AutoPushFrame:
        frame = self._pop_frame()
        if isinstance(frame, AutoPushFrame):
            return frame
        raise ProtocolError("expected auto-push")

    def read_frame(self, timeout: float | None = None) -> ResponseFrame | AutoPushFrame:
        frame = self._pop_frame()
        if isinstance(frame, ResponseFrame | AutoPushFrame):
            return frame
        raise frame

    def _pop_frame(self) -> ResponseFrame | AutoPushFrame:
        if not self.frames:
            raise AssertionError("No queued frame")
        frame = self.frames.pop(0)
        if isinstance(frame, Exception):
            raise frame
        return frame


def response(register: int, data: bytes = b"", function_code: int = 0x03) -> ResponseFrame:
    return ResponseFrame(
        function_code=function_code,
        register_address=register,
        data_length=len(data),
        data=data,
        raw_frame=b"raw-response",
    )


def auto_push(data: bytes) -> AutoPushFrame:
    return AutoPushFrame(
        frame_length=len(data) + 1,
        error_code=0,
        data=data,
        raw_frame=b"raw-auto",
    )


def board_with(fake: FakeTransport) -> HighSpeedBoard:
    return HighSpeedBoard("/dev/ttyUSB0", transport=fake)  # type: ignore[arg-type]


def module_force_payload() -> bytes:
    payload = bytearray()
    for index in range(28):
        payload.extend([index, 0x00, index + 1, 0x00, index + 2, 0x00])
    assert len(payload) == MODULE_FORCE_LENGTH
    return bytes(payload)


def test_context_manager_opens_and_closes_transport() -> None:
    fake = FakeTransport()

    with board_with(fake) as board:
        assert board.is_open

    assert fake.open_calls == 1
    assert fake.close_calls == 1
    assert not fake.is_open


def test_read_register_writes_request_and_returns_data() -> None:
    fake = FakeTransport([response(0x1234, b"AB")])
    board = board_with(fake)

    data = board.read_register(0x1234, 2)

    assert data == b"AB"
    assert fake.writes == [build_read_request(0x1234, 2)]


def test_read_register_rejects_response_register_mismatch() -> None:
    fake = FakeTransport([response(0x1235, b"AB")])
    board = board_with(fake)

    with pytest.raises(ProtocolError):
        board.read_register(0x1234, 2)


def test_write_register_writes_request_and_returns_response() -> None:
    fake = FakeTransport([response(AUTO_PUSH_REGISTER)])
    board = board_with(fake)

    frame = board.write_register(AUTO_PUSH_REGISTER, b"\x01")

    assert frame.register_address == AUTO_PUSH_REGISTER
    assert fake.writes == [build_write_request(AUTO_PUSH_REGISTER, b"\x01")]


def test_send_raw_frame_supports_response_auto_frame_and_no_read() -> None:
    response_frame = response(0x0017)
    auto_frame = auto_push(b"payload")
    any_frame = response(0x0000, b"v")
    fake = FakeTransport([response_frame, auto_frame, any_frame])
    board = board_with(fake)

    assert board.send_raw_frame(b"a", expected="response") == response_frame
    assert board.send_raw_frame(b"b", expected="auto") == auto_frame
    assert board.send_raw_frame(b"c", expected="frame") == any_frame
    assert board.send_raw_frame(b"d", expected=None) is None
    assert fake.writes == [b"a", b"b", b"c", b"d"]


def test_get_version_decodes_null_padded_ascii() -> None:
    fake = FakeTransport([response(VERSION_REGISTER, b"v1.2\x00\x00")])
    board = board_with(fake)

    assert board.get_version() == "v1.2"
    assert fake.writes == [build_read_request(VERSION_REGISTER, VERSION_LENGTH)]


def test_enable_disable_auto_push() -> None:
    fake = FakeTransport([response(AUTO_PUSH_REGISTER), response(AUTO_PUSH_REGISTER)])
    board = board_with(fake)

    assert board.enable_auto_push().register_address == AUTO_PUSH_REGISTER
    assert board.disable_auto_push().register_address == AUTO_PUSH_REGISTER
    assert fake.writes == [
        build_write_request(AUTO_PUSH_REGISTER, b"\x01"),
        build_write_request(AUTO_PUSH_REGISTER, b"\x00"),
    ]


def test_disable_auto_push_tolerates_timeout_after_write() -> None:
    fake = FakeTransport([FrameTimeoutError("timeout")])
    board = board_with(fake)

    assert board.disable_auto_push(timeout=0.01) is None
    assert fake.writes == [build_write_request(AUTO_PUSH_REGISTER, b"\x00")]


def test_calibrate_sends_default_or_custom_frame() -> None:
    fake = FakeTransport([response(0x0017), response(0x0017)])
    board = board_with(fake)

    board.calibrate()
    board.calibrate(b"custom")

    assert fake.writes == [DEFAULT_CALIBRATION_FRAME, b"custom"]


def test_reset_tolerates_timeout_after_write() -> None:
    fake = FakeTransport([FrameTimeoutError("timeout")])
    board = board_with(fake)

    assert board.reset(timeout=0.01) is None
    assert fake.writes == [build_write_request(SYSTEM_RESET_REGISTER, b"\x01")]


def test_get_connected_sensors_reads_status_registers() -> None:
    fake = FakeTransport(
        [
            response(SENSOR_STATUS_REGISTERS[0], b"\x41"),
            response(SENSOR_STATUS_REGISTERS[1], b"\x00"),
            response(SENSOR_STATUS_REGISTERS[2], b"\x00"),
            response(SENSOR_STATUS_REGISTERS[3], b"\x00"),
        ]
    )
    board = board_with(fake)

    status = board.get_connected_sensors()

    assert status.connected_sensors == (THUMB_NEAR, INDEX_TIP)
    assert fake.writes == [build_read_request(register, 1) for register in SENSOR_STATUS_REGISTERS]


def test_get_distribution_point_counts_reads_two_byte_counts() -> None:
    fake = FakeTransport(
        [
            response(get_point_count_register(THUMB_NEAR), (2).to_bytes(2, "little")),
            response(get_point_count_register(INDEX_TIP), (0).to_bytes(2, "little")),
        ]
    )
    board = board_with(fake)

    counts = board.get_distribution_point_counts((THUMB_NEAR, INDEX_TIP))

    assert counts == {THUMB_NEAR: 2, INDEX_TIP: 0}
    assert fake.writes == [
        build_read_request(get_point_count_register(THUMB_NEAR), 2),
        build_read_request(get_point_count_register(INDEX_TIP), 2),
    ]


def test_read_module_forces_reads_and_parses_force_block() -> None:
    fake = FakeTransport([response(MODULE_FORCE_REGISTER, module_force_payload())])
    board = board_with(fake)

    forces = board.read_module_forces()

    assert len(forces) == 28
    assert forces[0].sensor == THUMB_NEAR
    assert forces[0].force.raw_x == 0
    assert forces[6].sensor == INDEX_TIP
    assert forces[6].force.raw_x == 6
    assert board.state.get_module_force(INDEX_TIP) == forces[6]
    assert fake.writes == [build_read_request(MODULE_FORCE_REGISTER, MODULE_FORCE_LENGTH)]


def test_read_distribution_force_reads_count_module_force_and_distribution() -> None:
    distribution_start, _ = get_distribution_range(INDEX_TIP)
    fake = FakeTransport(
        [
            response(get_point_count_register(INDEX_TIP), (1).to_bytes(2, "little")),
            response(MODULE_FORCE_REGISTER, module_force_payload()),
            response(distribution_start, bytes([0x01, 0x02, 0x03])),
        ]
    )
    board = board_with(fake)

    reading = board.read_distribution_force(INDEX_TIP)

    assert reading.sensor == INDEX_TIP
    assert reading.total_force is not None
    assert reading.total_force.raw_x == 6
    assert len(reading.distribution) == 1
    assert reading.distribution[0].force.raw_z == 3
    assert fake.writes == [
        build_read_request(get_point_count_register(INDEX_TIP), 2),
        build_read_request(MODULE_FORCE_REGISTER, MODULE_FORCE_LENGTH),
        build_read_request(distribution_start, 3),
    ]


def test_read_connected_distribution_forces_reads_status_counts_modules_and_points() -> None:
    thumb_start, _ = get_distribution_range(THUMB_NEAR)
    index_start, _ = get_distribution_range(INDEX_TIP)
    fake = FakeTransport(
        [
            response(SENSOR_STATUS_REGISTERS[0], b"\x41"),
            response(SENSOR_STATUS_REGISTERS[1], b"\x00"),
            response(SENSOR_STATUS_REGISTERS[2], b"\x00"),
            response(SENSOR_STATUS_REGISTERS[3], b"\x00"),
            response(get_point_count_register(THUMB_NEAR), (1).to_bytes(2, "little")),
            response(get_point_count_register(INDEX_TIP), (1).to_bytes(2, "little")),
            response(MODULE_FORCE_REGISTER, module_force_payload()),
            response(thumb_start, bytes([0x01, 0x02, 0x03])),
            response(index_start, bytes([0x04, 0x05, 0x06])),
        ]
    )
    board = board_with(fake)

    readings = board.read_connected_distribution_forces()

    assert tuple(reading.sensor for reading in readings) == (THUMB_NEAR, INDEX_TIP)
    assert readings[0].total_force is not None
    assert readings[0].total_force.raw_x == 0
    assert readings[1].total_force is not None
    assert readings[1].total_force.raw_x == 6
    assert readings[1].distribution[0].force.raw_z == 6


def test_read_auto_push_readings_refreshes_missing_metadata() -> None:
    payload = b"\x01\x00\x02\x00\x03\x00" + bytes([0x04, 0x05, 0x06])
    fake = FakeTransport(
        [
            response(SENSOR_STATUS_REGISTERS[0], b"\x01"),
            response(SENSOR_STATUS_REGISTERS[1], b"\x00"),
            response(SENSOR_STATUS_REGISTERS[2], b"\x00"),
            response(SENSOR_STATUS_REGISTERS[3], b"\x00"),
            response(get_point_count_register(THUMB_NEAR), (1).to_bytes(2, "little")),
            auto_push(payload),
        ]
    )
    board = board_with(fake)

    readings = board.read_auto_push_readings()

    assert len(readings) == 1
    assert readings[0].sensor == THUMB_NEAR
    assert readings[0].total_force is not None
    assert readings[0].total_force.raw_x == 1
    assert readings[0].distribution[0].force.raw_z == 6


def test_read_auto_push_readings_accepts_explicit_metadata() -> None:
    payload = b"\x01\x00\x02\x00\x03\x00" + bytes([0x04, 0x05, 0x06])
    fake = FakeTransport([auto_push(payload)])
    board = board_with(fake)

    readings = board.read_auto_push_readings(
        connected_sensors=(THUMB_NEAR,),
        point_counts={THUMB_NEAR: 1},
    )

    assert readings[0].sensor == THUMB_NEAR
    assert board.state.get_sensor(THUMB_NEAR) == readings[0]
    assert fake.writes == []


def test_read_auto_push_readings_can_skip_state_update() -> None:
    payload = b"\x01\x00\x02\x00\x03\x00"
    fake = FakeTransport([auto_push(payload)])
    board = board_with(fake)

    board.read_auto_push_readings(
        connected_sensors=(THUMB_NEAR,),
        point_counts={THUMB_NEAR: 0},
        update_state=False,
    )

    assert board.state.get_sensor(THUMB_NEAR) is None


def test_read_auto_push_readings_applies_palm_point_limit() -> None:
    payload = b"\x00" * 6 + bytes(range(27))
    fake = FakeTransport([auto_push(payload)])
    board = board_with(fake)

    readings = board.read_auto_push_readings(
        connected_sensors=(PALM_8,),
        point_counts={PALM_8: 10},
    )

    assert len(readings[0].distribution) == 9


def test_iter_auto_push_frames_yields_frames() -> None:
    fake = FakeTransport([auto_push(b"a"), auto_push(b"b")])
    board = board_with(fake)
    frames = board.iter_auto_push_frames()

    assert next(frames).data == b"a"
    assert next(frames).data == b"b"
