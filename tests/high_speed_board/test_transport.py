import pytest

import paxini_utils.high_speed_board.transport as transport_module
from paxini_utils.high_speed_board.errors import FrameTimeoutError, ProtocolError, TransportError
from paxini_utils.high_speed_board.protocol import calculate_lrc
from paxini_utils.high_speed_board.transport import SerialTransport


class FakeSerial:
    def __init__(
        self,
        *args: object,
        read_chunks: list[bytes] | None = None,
        write_result: int | None = None,
        read_error: Exception | None = None,
        write_error: Exception | None = None,
        close_error: Exception | None = None,
        **kwargs: object,
    ) -> None:
        self.args = args
        self.kwargs = kwargs
        self.read_chunks = read_chunks or []
        self.write_result = write_result
        self.read_error = read_error
        self.write_error = write_error
        self.close_error = close_error
        self.writes: list[bytes] = []
        self.timeout = kwargs.get("timeout")
        self.is_open = True

    def read(self, size: int) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        if not self.read_chunks:
            return b""
        return self.read_chunks.pop(0)

    def write(self, frame: bytes) -> int:
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(frame)
        return self.write_result if self.write_result is not None else len(frame)

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.is_open = False


def with_lrc(frame_body: bytes) -> bytes:
    return frame_body + bytes([calculate_lrc(frame_body)])


def response_frame(data: bytes = b"AB") -> bytes:
    body = b"\xAA\x55\x00\x03\x34\x12" + len(data).to_bytes(2, "little") + data
    return with_lrc(body)


def auto_push_frame(data: bytes = b"XY") -> bytes:
    frame_length = len(data) + 1
    body = b"\xAA\x56\x00" + frame_length.to_bytes(2, "little") + b"\x00" + data
    return with_lrc(body)


def install_fake_serial(monkeypatch: pytest.MonkeyPatch, fake: FakeSerial) -> None:
    def build_fake_serial(**kwargs: object) -> FakeSerial:
        fake.kwargs = kwargs
        return fake

    monkeypatch.setattr(transport_module, "Serial", build_fake_serial)


def test_open_and_close_use_serial_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial()
    install_fake_serial(monkeypatch, fake)

    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    assert transport.is_open
    assert fake.kwargs["port"] == "/dev/ttyUSB0"
    assert fake.kwargs["baudrate"] == 921_600
    assert fake.kwargs["bytesize"] == 8
    assert fake.kwargs["parity"] == "N"
    assert fake.kwargs["stopbits"] == 1

    transport.close()

    assert not transport.is_open
    assert not fake.is_open


def test_context_manager_opens_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial()
    install_fake_serial(monkeypatch, fake)

    with SerialTransport("/dev/cu.usbserial-110") as transport:
        assert transport.is_open

    assert not fake.is_open


def test_write_requires_open_transport() -> None:
    transport = SerialTransport("/dev/ttyUSB0")

    with pytest.raises(TransportError):
        transport.write(b"frame")


def test_read_requires_open_transport() -> None:
    transport = SerialTransport("/dev/ttyUSB0")

    with pytest.raises(TransportError):
        transport.read_frame()


def test_write_sends_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial()
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    transport.write(b"frame")

    assert fake.writes == [b"frame"]


def test_write_rejects_partial_write(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(write_result=2)
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    with pytest.raises(TransportError):
        transport.write(b"frame")


def test_read_response_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_chunks=[response_frame()])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    frame = transport.read_response()

    assert frame.register_address == 0x1234
    assert frame.data == b"AB"


def test_read_auto_push_parses_valid_auto_push(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_chunks=[auto_push_frame()])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    frame = transport.read_auto_push()

    assert frame.data == b"XY"


def test_read_frame_drops_garbage_before_header(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_chunks=[b"garbage" + response_frame(b"C")])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    frame = transport.read_response()

    assert frame.data == b"C"


def test_read_frame_handles_partial_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = response_frame(b"D")
    fake = FakeSerial(read_chunks=[frame[:3], frame[3:7], frame[7:]])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    parsed = transport.read_response()

    assert parsed.data == b"D"


def test_read_frame_preserves_remaining_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    first = response_frame(b"1")
    second = response_frame(b"2")
    fake = FakeSerial(read_chunks=[first + second])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    assert transport.read_response().data == b"1"
    assert transport.read_response().data == b"2"


def test_read_frame_times_out_on_incomplete_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_chunks=[response_frame()[:4]])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    with pytest.raises(FrameTimeoutError):
        transport.read_response(timeout=0.001)


def test_read_response_rejects_auto_push_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_chunks=[auto_push_frame()])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    with pytest.raises(ProtocolError):
        transport.read_response()


def test_read_auto_push_rejects_response_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_chunks=[response_frame()])
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    with pytest.raises(ProtocolError):
        transport.read_auto_push()


def test_open_wraps_serial_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_open_error(**kwargs: object) -> FakeSerial:
        raise OSError("open failed")

    monkeypatch.setattr(transport_module, "Serial", raise_open_error)

    with pytest.raises(TransportError):
        SerialTransport("/dev/ttyUSB0").open()


def test_read_wraps_serial_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(read_error=OSError("read failed"))
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    with pytest.raises(TransportError):
        transport.read_response()


def test_write_wraps_serial_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial(write_error=OSError("write failed"))
    install_fake_serial(monkeypatch, fake)
    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()

    with pytest.raises(TransportError):
        transport.write(b"frame")
