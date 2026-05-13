"""Player movement on a grid (logic stays top-down; rendering is isometric)."""

from typing import List, Tuple

from kitchen import Cell, walkable


class Player:
    def __init__(self, col: float, row: float) -> None:
        self.col = float(col)
        self.row = float(row)
        self.speed = 6.0

    def center_tile(self) -> Tuple[int, int]:
        return int(round(self.col)), int(round(self.row))

    def update(
        self,
        cells: List[List[Cell]],
        dx: float,
        dy: float,
        dt: float,
    ) -> None:
        if dx == 0 and dy == 0:
            return
        length = (dx * dx + dy * dy) ** 0.5
        nx = dx / length
        ny = dy / length
        step = self.speed * dt
        ncol = self.col + nx * step
        nrow = self.row + ny * step

        if walkable(cells, int(round(ncol)), int(round(self.row))):
            self.col = ncol
        if walkable(cells, int(round(self.col)), int(round(nrow))):
            self.row = nrow
