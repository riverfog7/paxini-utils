# paxini-utils

Utilities for Paxini hardware integrations.

## High Speed Board

The high speed board API supports synchronous register commands, sensor force parsing,
auto-push polling, optional state caching, and background streaming callbacks.

### Serial Ports

Pass the serial device path for your platform:

```python
from paxini_utils.high_speed_board import HighSpeedBoard

board = HighSpeedBoard("/dev/cu.usbserial-110")  # macOS
board = HighSpeedBoard("/dev/ttyUSB0")           # Linux USB serial
board = HighSpeedBoard("/dev/ttyACM0")           # Linux ACM device
```

The default serial settings are `921600` baud, 8 data bits, no parity, 1 stop bit.

### Basic Usage

```python
from paxini_utils.high_speed_board import HighSpeedBoard

with HighSpeedBoard("/dev/ttyUSB0") as board:
    version = board.get_version()
    status = board.get_connected_sensors()
    module_forces = board.read_module_forces()

    print(version)
    print(status.connected_sensors)
    print(module_forces[0].sensor, module_forces[0].force)
```

### Register Access

```python
from paxini_utils.high_speed_board import HighSpeedBoard

with HighSpeedBoard("/dev/ttyUSB0") as board:
    raw = board.read_register(0x0000, 15)
    response = board.write_register(0x0017, b"\x01")
```

### Sensor Reads

```python
from paxini_utils.high_speed_board import HighSpeedBoard
from paxini_utils.high_speed_board.constants import INDEX_TIP

with HighSpeedBoard("/dev/ttyUSB0") as board:
    reading = board.read_distribution_force(INDEX_TIP)

    print(reading.total_force)
    for point in reading.distribution:
        print(point.index, point.force)
```

Read all connected sensors:

```python
with HighSpeedBoard("/dev/ttyUSB0") as board:
    readings = board.read_connected_distribution_forces()
```

### Auto-Push Polling

```python
with HighSpeedBoard("/dev/ttyUSB0") as board:
    board.enable_auto_push()

    readings = board.read_auto_push_readings()

    board.disable_auto_push()
```

`read_auto_push_readings()` refreshes connected sensors and point counts on first use
if they are not already cached.

### Background Streaming

```python
from paxini_utils.high_speed_board import HighSpeedBoard


def on_reading(reading):
    print(reading.sensor, reading.total_force)


def on_error(exc):
    print("stream error", exc)


with HighSpeedBoard("/dev/ttyUSB0") as board:
    board.enable_auto_push()
    handle = board.start_streaming(on_reading=on_reading, on_error=on_error)

    # ... do application work ...

    handle.stop()
    handle.join(timeout=1)
    board.disable_auto_push()
```

Streaming updates `board.state` before invoking callbacks by default.

### State Cache

```python
with HighSpeedBoard("/dev/ttyUSB0") as board:
    board.read_auto_push_readings()
    latest = board.state.get_sensor("thumb_near")
    snapshot = board.state.snapshot()
```

The cache stores latest values only. It is protected by a lock for background
streaming use.

### Calibration And Reset

```python
with HighSpeedBoard("/dev/ttyUSB0") as board:
    board.calibrate()
    board.calibrate(bytes.fromhex("55AA00170200010001E6"))
    board.reset()
```

`disable_auto_push()` and `reset()` tolerate no response after a successful write,
matching the reference behavior.
