from threading import Event

from paxini_utils.high_speed_board.constants import THUMB_NEAR
from paxini_utils.high_speed_board.models import AutoPushFrame, Force3D, ModuleForce, SensorReading
from paxini_utils.high_speed_board.state import BoardState
from paxini_utils.high_speed_board.streaming import StreamingHandle


def force(raw_x: int = 1) -> Force3D:
    return Force3D(
        x=raw_x * 0.1,
        y=0.0,
        z=0.0,
        raw_x=raw_x,
        raw_y=0,
        raw_z=0,
        raw_bytes=bytes([raw_x, 0, 0, 0, 0, 0]),
    )


def reading(sensor: str = THUMB_NEAR, raw_x: int = 1) -> SensorReading:
    return SensorReading(sensor=sensor, total_force=force(raw_x))


def frame(data: bytes = b"payload") -> AutoPushFrame:
    return AutoPushFrame(frame_length=len(data) + 1, error_code=0, data=data, raw_frame=b"raw")


def test_board_state_updates_and_snapshots_latest_values() -> None:
    state = BoardState()
    first = reading(raw_x=1)
    second = reading(raw_x=2)
    module_force = ModuleForce(sensor=THUMB_NEAR, force=force(3))

    state.update_readings((first,))
    state.update_readings((second,))
    state.update_module_forces((module_force,))
    snapshot = state.snapshot()

    assert state.get_sensor(THUMB_NEAR) == second
    assert state.get_module_force(THUMB_NEAR) == module_force
    assert snapshot.sensor_readings == (second,)
    assert snapshot.module_forces == (module_force,)


def test_board_state_clear_removes_cached_values() -> None:
    state = BoardState()
    state.update_readings((reading(),))
    state.update_module_forces((ModuleForce(sensor=THUMB_NEAR, force=force()),))

    state.clear()

    assert state.get_sensor(THUMB_NEAR) is None
    assert state.get_module_force(THUMB_NEAR) is None
    assert state.snapshot().sensor_readings == ()
    assert state.snapshot().module_forces == ()


def test_streaming_handle_calls_callbacks_and_stops() -> None:
    start_event = Event()
    frames: list[AutoPushFrame] = []
    readings_batches: list[tuple[SensorReading, ...]] = []
    individual_readings: list[SensorReading] = []

    def read_once() -> tuple[AutoPushFrame, tuple[SensorReading, ...]]:
        start_event.wait(1)
        return frame(b"one"), (reading(),)

    handle = StreamingHandle(
        read_once=read_once,
        on_frame=frames.append,
        on_readings=readings_batches.append,
        on_reading=individual_readings.append,
    )

    def stop_after_reading(value: SensorReading) -> None:
        individual_readings.append(value)
        handle.stop()

    handle = StreamingHandle(
        read_once=read_once,
        on_frame=frames.append,
        on_readings=readings_batches.append,
        on_reading=stop_after_reading,
    ).start()
    start_event.set()
    handle.join(1)

    assert not handle.is_running
    assert len(frames) == 1
    assert len(readings_batches) == 1
    assert individual_readings == [reading()]


def test_streaming_handle_reports_errors_and_continues_until_stopped() -> None:
    start_event = Event()
    errors: list[Exception] = []
    handle_holder: dict[str, StreamingHandle] = {}

    def read_once() -> tuple[AutoPushFrame, tuple[SensorReading, ...]]:
        start_event.wait(1)
        raise RuntimeError("boom")

    def on_error(exc: Exception) -> None:
        errors.append(exc)
        handle_holder["handle"].stop()

    handle = StreamingHandle(read_once=read_once, on_error=on_error)
    handle_holder["handle"] = handle
    handle.start()
    start_event.set()
    handle.join(1)

    assert not handle.is_running
    assert len(errors) == 1
    assert str(errors[0]) == "boom"
    assert handle.last_error == errors[0]
