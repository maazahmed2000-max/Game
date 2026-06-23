"""Lab tech movement on a grid (top-down logic, isometric view)."""

import math
from typing import List, Optional, Tuple

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
        self.carrying_order_idx: Optional[int] = None
        self.facing_right = True
        self.facing_mirror = False

    def _update_facing(self, dx: float, dy: float) -> None:
        """D = right sheet; A = right sheet mirrored; S = left sheet (old A)."""
        if dx > 0:
            self.facing_right = True
            self.facing_mirror = False
        elif dx < 0:
            self.facing_right = True
            self.facing_mirror = True
        elif dy > 0:
            self.facing_right = False
            self.facing_mirror = False

    def center_tile(self) -> Tuple[int, int]:
        return int(round(self.col)), int(round(self.row))

    def drop_wafer(self) -> None:
        self.carrying_wafer = False
        self.carrying_order_idx = None

    def update(
        self,
        cells: List[List[Cell]],
        dx: float,
        dy: float,
        dt: float,
    ) -> None:
        if dx == 0 and dy == 0:
            return
        self._update_facing(dx, dy)
        gx, gy = screen_input_to_grid(dx, dy)
        length = math.hypot(gx, gy)
        if length == 0:
            return
        nx, ny = gx / length, gy / length
        step = self.speed * dt
        ncol = self.col + nx * step
        nrow = self.row + ny * step

        if walkable(cells, ncol, self.row):
            self.col = ncol
        if walkable(cells, self.col, nrow):
            self.row = nrow
