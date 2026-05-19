"""Thread-safe latest-value state cache for board readings."""

from threading import RLock

from paxini_utils.high_speed_board.models import BoardStateSnapshot, ModuleForce, SensorReading


class BoardState:
    """Store latest sensor readings and module forces."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sensor_readings: dict[str, SensorReading] = {}
        self._module_forces: dict[str, ModuleForce] = {}

    def clear(self) -> None:
        """Clear all cached latest values."""
        with self._lock:
            self._sensor_readings.clear()
            self._module_forces.clear()

    def update_readings(self, readings: tuple[SensorReading, ...]) -> None:
        """Update latest sensor readings."""
        with self._lock:
            for reading in readings:
                self._sensor_readings[reading.sensor] = reading

    def update_module_forces(self, module_forces: tuple[ModuleForce, ...]) -> None:
        """Update latest module forces."""
        with self._lock:
            for module_force in module_forces:
                self._module_forces[module_force.sensor] = module_force

    def get_sensor(self, sensor: str) -> SensorReading | None:
        """Return the latest reading for a sensor, if present."""
        with self._lock:
            return self._sensor_readings.get(sensor)

    def get_module_force(self, sensor: str) -> ModuleForce | None:
        """Return the latest module force for a sensor, if present."""
        with self._lock:
            return self._module_forces.get(sensor)

    def snapshot(self) -> BoardStateSnapshot:
        """Return an immutable snapshot of cached values."""
        with self._lock:
            return BoardStateSnapshot(
                sensor_readings=tuple(self._sensor_readings.values()),
                module_forces=tuple(self._module_forces.values()),
            )
