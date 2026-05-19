"""Lab tech movement on a grid (top-down logic, isometric view)."""

import math
from typing import List, Tuple

from lab import Cell, walkable


def screen_input_to_grid(dx: float, dy: float) -> Tuple[float, float]:
    """Map screen WASD / stick input to isometric grid axes.

    S/W move down/up on screen (both col and row), A/D move left/right.
    """
    return dx + dy, dy - dx

class Player:
    def __init__(self, col: float, row: float) -> None:
        self.col = float(col)
        self.row = float(row)
        self.speed = 6.0
        self.carrying_wafer = False
        self.facing_right = True

    def center_tile(self) -> Tuple[int, int]:
        return int(round(self.col)), int(round(self.row))

    def drop_wafer(self) -> None:
        self.carrying_wafer = False

    def update(
        self,
        cells: List[List[Cell]],
        dx: float,
        dy: float,
        dt: float,
    ) -> None:
        if dx == 0 and dy == 0:
            return
        if dx != 0:
            self.facing_right = dx > 0
        gx, gy = screen_input_to_grid(dx, dy)
        length = math.hypot(gx, gy)
        if length == 0:
            return
        nx, ny = gx / length, gy / length
        step = self.speed * dt
        ncol = self.col + nx * step
        nrow = self.row + ny * step

        if walkable(cells, int(round(ncol)), int(round(self.row))):
            self.col = ncol
        if walkable(cells, int(round(self.col)), int(round(nrow))):
            self.row = nrow
