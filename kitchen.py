"""Tile map, station types, and simple recipe rules."""

from enum import Enum, auto
from typing import List, Optional, Tuple

from constants import COLS, ROWS


class Cell(Enum):
    FLOOR = auto()
    WALL = auto()
    INGREDIENT_BIN = auto()  # pick raw patty
    CHOP = auto()
    STOVE = auto()
    PLATE = auto()
    SERVE = auto()


# Recipe: ordered list of station steps (what must be done before serve)
RECIPE_BURGER: Tuple[Cell, ...] = (
    Cell.INGREDIENT_BIN,
    Cell.CHOP,
    Cell.STOVE,
    Cell.PLATE,
    Cell.SERVE,
)


def default_map() -> List[List[Cell]]:
    g: List[List[Cell]] = [[Cell.FLOOR for _ in range(COLS)] for _ in range(ROWS)]

    for c in range(COLS):
        g[0][c] = Cell.WALL
        g[ROWS - 1][c] = Cell.WALL
    for r in range(ROWS):
        g[r][0] = Cell.WALL
        g[r][COLS - 1] = Cell.WALL

    # Counter island
    for c in range(4, 10):
        g[4][c] = Cell.WALL

    # Stations (walkable tiles with special behavior)
    g[3][3] = Cell.INGREDIENT_BIN
    g[3][6] = Cell.CHOP
    g[3][9] = Cell.STOVE
    g[6][6] = Cell.PLATE
    g[6][11] = Cell.SERVE

    return g


def walkable(cells: List[List[Cell]], col: int, row: int) -> bool:
    if not (0 <= col < COLS and 0 <= row < ROWS):
        return False
    return cells[row][col] != Cell.WALL


def station_at(cells: List[List[Cell]], col: int, row: int) -> Optional[Cell]:
    if not (0 <= col < COLS and 0 <= row < ROWS):
        return None
    c = cells[row][col]
    if c in (
        Cell.INGREDIENT_BIN,
        Cell.CHOP,
        Cell.STOVE,
        Cell.PLATE,
        Cell.SERVE,
    ):
        return c
    return None


class Order:
    """One burger order with a time limit."""

    def __init__(self, recipe: Tuple[Cell, ...], time_left: float) -> None:
        self.recipe = recipe
        self.time_left = time_left
        self.completed_steps: List[Cell] = []

    def next_expected(self) -> Optional[Cell]:
        idx = len(self.completed_steps)
        if idx >= len(self.recipe):
            return None
        return self.recipe[idx]

    def apply_station(self, st: Cell) -> bool:
        expected = self.next_expected()
        if expected is None or st != expected:
            return False
        self.completed_steps.append(st)
        return True

    def is_done(self) -> bool:
        return len(self.completed_steps) >= len(self.recipe)

    def progress_text(self) -> str:
        names = {
            Cell.INGREDIENT_BIN: "bin",
            Cell.CHOP: "chop",
            Cell.STOVE: "stove",
            Cell.PLATE: "plate",
            Cell.SERVE: "serve",
        }
        parts = []
        for i, step in enumerate(self.recipe):
            label = names[step]
            if i < len(self.completed_steps):
                parts.append(f"[{label}]")
            elif i == len(self.completed_steps):
                parts.append(f"->{label}")
            else:
                parts.append(label)
        return " ".join(parts)
