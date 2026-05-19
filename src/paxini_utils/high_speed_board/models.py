"""Pydantic models returned by the high speed board API."""

from pydantic import BaseModel, ConfigDict, Field


class Force3D(BaseModel):
    """A parsed three-axis force value."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    z: float
    raw_x: int
    raw_y: int
    raw_z: int
    raw_bytes: bytes


class DistributionPoint(BaseModel):
    """One distribution-force point for a sensor."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    force: Force3D
    raw_bytes: bytes


class ModuleForce(BaseModel):
    """Latest total force for one physical sensor module."""

    model_config = ConfigDict(frozen=True)
    sensor: str
    force: Force3D


class SensorReading(BaseModel):
    """Parsed reading for one sensor."""

    model_config = ConfigDict(frozen=True)
    sensor: str
    total_force: Force3D | None = None
    distribution: tuple[DistributionPoint, ...] = ()


class ResponseFrame(BaseModel):
    """Parsed normal AA55 response frame."""

    model_config = ConfigDict(frozen=True)
    function_code: int
    register_address: int
    data_length: int = Field(ge=0)
    data: bytes
    raw_frame: bytes


class AutoPushFrame(BaseModel):
    """Parsed AA56 automatic push frame."""

    model_config = ConfigDict(frozen=True)
    frame_length: int = Field(ge=0)
    error_code: int
    data: bytes
    raw_frame: bytes


class BoardStatus(BaseModel):
    """Current board status derived from status registers."""

    model_config = ConfigDict(frozen=True)
    connected_sensors: tuple[str, ...] = ()


class BoardStateSnapshot(BaseModel):
    """Immutable snapshot of latest cached board values."""

    model_config = ConfigDict(frozen=True)
    sensor_readings: tuple[SensorReading, ...] = ()
    module_forces: tuple[ModuleForce, ...] = ()
