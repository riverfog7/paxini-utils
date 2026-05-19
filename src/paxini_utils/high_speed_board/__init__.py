"""High speed communication board support."""

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
    DistributionPoint,
    Force3D,
    ModuleForce,
    ResponseFrame,
    SensorReading,
)

__all__ = [
    "AutoPushFrame",
    "BoardError",
    "BoardStatus",
    "ChecksumError",
    "DeviceError",
    "DistributionPoint",
    "Force3D",
    "FrameTimeoutError",
    "ModuleForce",
    "ProtocolError",
    "ResponseFrame",
    "SensorReading",
    "TransportError",
    "parse_auto_push_frame",
    "parse_response_frame",
    "validate_lrc",
]
