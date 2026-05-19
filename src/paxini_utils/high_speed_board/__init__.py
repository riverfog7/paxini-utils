"""High speed communication board support."""

from paxini_utils.high_speed_board.client import HighSpeedBoard
from paxini_utils.high_speed_board.errors import (
    BoardError,
    ChecksumError,
    DeviceError,
    FrameTimeoutError,
    ProtocolError,
    TransportError,
)
from paxini_utils.high_speed_board.frames import (
    parse_auto_push_frame,
    parse_response_frame,
    validate_lrc,
)
from paxini_utils.high_speed_board.models import (
    AutoPushFrame,
    BoardStatus,
    BoardStateSnapshot,
    DistributionPoint,
    Force3D,
    ModuleForce,
    ResponseFrame,
    SensorReading,
)
from paxini_utils.high_speed_board.parsing import (
    parse_auto_push_readings,
    parse_distribution_points,
    parse_module_forces,
    parse_sensor_reading,
    parse_total_force,
)
from paxini_utils.high_speed_board.state import BoardState
from paxini_utils.high_speed_board.streaming import StreamingHandle
from paxini_utils.high_speed_board.transport import SerialTransport

__all__ = [
    "AutoPushFrame",
    "BoardError",
    "BoardState",
    "BoardStateSnapshot",
    "BoardStatus",
    "ChecksumError",
    "DeviceError",
    "DistributionPoint",
    "Force3D",
    "FrameTimeoutError",
    "HighSpeedBoard",
    "ModuleForce",
    "ProtocolError",
    "ResponseFrame",
    "SensorReading",
    "SerialTransport",
    "StreamingHandle",
    "TransportError",
    "parse_auto_push_frame",
    "parse_auto_push_readings",
    "parse_distribution_points",
    "parse_module_forces",
    "parse_response_frame",
    "parse_sensor_reading",
    "parse_total_force",
    "validate_lrc",
]
