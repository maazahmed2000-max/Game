"""Simple lab coworker patrol — bumping them while carrying a wafer causes a drop."""

from __future__ import annotations

import math
from typing import List, Tuple

from lab import Cell, walkable


class Coworker:
    def __init__(self, col_a: float, row_a: float, col_b: float, row_b: float, speed: float = 1.1) -> None:
        self.a = (float(col_a), float(row_a))
        self.b = (float(col_b), float(row_b))
        self.col, self.row = self.a
        self.speed = speed
        self._phase = 0.0

    def update(self, cells: List[List[Cell]], dt: float) -> None:
        self._phase += dt * self.speed
        u = self._phase % 2.0
        if u > 1.0:
            u = 2.0 - u
        self.col = self.a[0] + (self.b[0] - self.a[0]) * u
        self.row = self.a[1] + (self.b[1] - self.a[1]) * u
        if not walkable(cells, int(round(self.col)), int(round(self.row))):
            self.col, self.row = self.a

    def grid_pos(self) -> Tuple[float, float]:
        return self.col, self.row
