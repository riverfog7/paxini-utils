"""Realtime distribution-force heatmap demo for the high speed board.

This intentionally polls distribution-force registers directly instead of using
auto-push frames, matching the notebook demo's register-read path.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ is required. Run with `uv run python demo/realtime_heatmap.py ...`.")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paxini_utils.high_speed_board import HighSpeedBoard, SensorReading
from paxini_utils.high_speed_board.constants import SENSOR_DISPLAY_NAMES, SENSOR_ORDER


DEFAULT_INTERVAL_MS = 75
DEFAULT_CELL_SIZE = 34
DEFAULT_MAX_FORCE = 25.0
COMPONENTS = ("x", "y", "z")
HEAT_PALETTE = (
    (8, 13, 30),
    (33, 92, 175),
    (0, 194, 168),
    (255, 211, 105),
    (255, 252, 235),
)


@dataclass(frozen=True)
class GridShape:
    rows: int
    columns: int


def infer_grid_shape(point_count: int) -> GridShape:
    """Return a compact rectangular grid for an ordered point list."""
    if point_count == 77:
        return GridShape(rows=9, columns=9)
    if point_count <= 0:
        return GridShape(rows=1, columns=1)
    columns = math.ceil(math.sqrt(point_count))
    rows = math.ceil(point_count / columns)
    return GridShape(rows=rows, columns=columns)


def grid_point_index(grid_index: int, shape: GridShape, point_count: int) -> int | None:
    if point_count == 77 and shape == GridShape(rows=9, columns=9):
        row, column = divmod(grid_index, shape.columns)
        if (row, column) in {(0, 0), (0, 8), (8, 0), (8, 8)}:
            return None
        corners_before = sum(
            1
            for corner in (0, 8, 72, 80)
            if corner < grid_index
        )
        return grid_index - corners_before
    return grid_index


def force_value(reading: SensorReading, point_index: int | None, component: str) -> float:
    if point_index is None:
        return 0.0
    if point_index >= len(reading.distribution):
        return 0.0
    force = reading.distribution[point_index].force
    return getattr(force, component)


def heat_color(value: float, max_force: float) -> str:
    """Map force magnitude to a dark blue -> teal -> warm white color ramp."""
    if max_force <= 0:
        max_force = DEFAULT_MAX_FORCE
    normalized = min(1.0, max(0.0, abs(value) / max_force))
    scaled = normalized * (len(HEAT_PALETTE) - 1)
    index = min(len(HEAT_PALETTE) - 2, int(scaled))
    ratio = scaled - index
    start = HEAT_PALETTE[index]
    end = HEAT_PALETTE[index + 1]
    red, green, blue = (
        int(start[channel] + (end[channel] - start[channel]) * ratio)
        for channel in range(3)
    )
    return f"#{red:02x}{green:02x}{blue:02x}"


class HeatmapApp:
    def __init__(
        self,
        board: HighSpeedBoard,
        sensors: tuple[str, ...],
        interval_ms: int,
        cell_size: int,
        component: str,
        max_force: float,
    ) -> None:
        self.board = board
        self.sensors = sensors
        self.interval_ms = interval_ms
        self.cell_size = cell_size
        self.component = component
        self.max_force = max_force
        self.running = True
        self.frame_index = 0
        self.last_error: str | None = None

        self.root = tk.Tk()
        self.root.title("Paxini Realtime Sensor Heatmaps")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="Starting...")
        self.canvas_by_sensor: dict[str, tk.Canvas] = {}
        self.shape_by_sensor: dict[str, GridShape] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text=f"Component: F{self.component} | Refresh: {self.interval_ms} ms | Max: {self.max_force:g} N",
        ).pack(side=tk.LEFT)
        ttk.Button(header, text="Stop", command=self.close).pack(side=tk.RIGHT)

        body = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        body.pack(fill=tk.BOTH, expand=True)

        for index, sensor in enumerate(self.sensors):
            frame = ttk.LabelFrame(body, text=SENSOR_DISPLAY_NAMES.get(sensor, sensor), padding=8)
            frame.grid(row=index, column=0, padx=6, pady=6, sticky="nsew")
            body.rowconfigure(index, weight=1)

            shape = self.shape_by_sensor.get(sensor, GridShape(rows=1, columns=1))
            canvas = tk.Canvas(
                frame,
                width=shape.columns * self.cell_size,
                height=shape.rows * self.cell_size,
                background="#050816",
                highlightthickness=1,
                highlightbackground="#1f2937",
            )
            canvas.pack()
            self.canvas_by_sensor[sensor] = canvas
        body.columnconfigure(0, weight=1)

        footer = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        footer.pack(fill=tk.X)
        ttk.Label(footer, textvariable=self.status_var).pack(side=tk.LEFT)

    def start(self) -> None:
        self.root.after(0, self._poll_once)
        self.root.mainloop()

    def close(self) -> None:
        self.running = False
        try:
            self.board.close()
        finally:
            self.root.destroy()

    def _poll_once(self) -> None:
        if not self.running:
            return

        started = time.monotonic()
        try:
            readings = tuple(
                self.board.read_distribution_force(
                    sensor,
                    refresh_point_count=False,
                )
                for sensor in self.sensors
            )
            self.frame_index += 1
            for reading in readings:
                self._draw_reading(reading)
            elapsed_ms = (time.monotonic() - started) * 1000.0
            self.status_var.set(
                f"Frame {self.frame_index} | {time.strftime('%H:%M:%S')} | read {elapsed_ms:.1f} ms"
            )
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - keep the UI alive while the board is noisy.
            self.last_error = str(exc)
            self.status_var.set(f"Read error: {self.last_error}")

        self.root.after(self.interval_ms, self._poll_once)

    def _draw_reading(self, reading: SensorReading) -> None:
        canvas = self.canvas_by_sensor[reading.sensor]
        shape = infer_grid_shape(len(reading.distribution))
        if self.shape_by_sensor.get(reading.sensor) != shape:
            self.shape_by_sensor[reading.sensor] = shape
            canvas.configure(
                width=shape.columns * self.cell_size,
                height=shape.rows * self.cell_size,
            )
        canvas.delete("all")

        for index in range(shape.rows * shape.columns):
            row, column = divmod(index, shape.columns)
            x0 = column * self.cell_size
            y0 = row * self.cell_size
            x1 = x0 + self.cell_size
            y1 = y0 + self.cell_size
            point_index = grid_point_index(index, shape, len(reading.distribution))
            if point_index is None:
                continue
            value = force_value(reading, point_index, self.component)
            canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=heat_color(value, self.max_force),
                outline="#111827",
            )
            if point_index < len(reading.distribution):
                effective_max = self.max_force if self.max_force > 0 else DEFAULT_MAX_FORCE
                text_color = "#111111" if abs(value) / effective_max > 0.72 else "#f8fafc"
                canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=f"{value:.1f}",
                    fill=text_color,
                    font=("TkDefaultFont", 9),
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize realtime distribution-force heatmaps from a Paxini high speed board.",
    )
    parser.add_argument("port", help="Serial port, for example /dev/cu.usbmodem750A687485311")
    parser.add_argument(
        "--sensor",
        action="append",
        choices=SENSOR_ORDER,
        help="Sensor to display. Repeat for multiple sensors. Defaults to all connected sensors.",
    )
    parser.add_argument(
        "--component",
        choices=COMPONENTS,
        default="z",
        help="Force component to display per distribution point.",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=DEFAULT_INTERVAL_MS,
        help="Polling interval in milliseconds.",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=DEFAULT_CELL_SIZE,
        help="Cell size in pixels.",
    )
    parser.add_argument(
        "--max-force",
        type=float,
        default=DEFAULT_MAX_FORCE,
        help="Force magnitude mapped to the hottest color.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    board = HighSpeedBoard(args.port)
    board.open()

    connected = board.get_connected_sensors().connected_sensors
    sensors = tuple(args.sensor) if args.sensor else connected
    if not sensors:
        board.close()
        raise SystemExit("No connected sensors found.")
    missing = tuple(sensor for sensor in sensors if sensor not in connected)
    if missing:
        board.close()
        raise SystemExit(f"Requested sensors are not connected: {', '.join(missing)}")

    board.get_distribution_point_counts(sensors)
    app = HeatmapApp(
        board=board,
        sensors=sensors,
        interval_ms=args.interval_ms,
        cell_size=args.cell_size,
        component=args.component,
        max_force=args.max_force,
    )
    app.start()


if __name__ == "__main__":
    main()
