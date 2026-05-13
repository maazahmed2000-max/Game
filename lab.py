"""PSI Quantum–style wafer test floor: stations, wafer orders, and test recipes."""

from __future__ import annotations

import random
from enum import Enum, auto
from typing import List, Optional, Tuple

from constants import COLS, ROWS


class Cell(Enum):
    FLOOR = auto()
    WALL = auto()
    RECEIVING = auto()  # pick up incoming wafer
    PROBER_LOAD = auto()  # load cassette into prober
    PROBER_WAIT = auto()  # cassette inventory / map — stand here for progress
    TEST_BENCH = auto()  # set E / O / EO / Oband / Cband / Other
    TEST_CHAMBER = auto()  # automated test run — progress bar
    FINISHED_RACK = auto()  # completed wafers


# One wafer’s linear route through the lab
RECIPE_WAFER: Tuple[Cell, ...] = (
    Cell.RECEIVING,
    Cell.PROBER_LOAD,
    Cell.PROBER_WAIT,
    Cell.TEST_BENCH,
    Cell.TEST_CHAMBER,
    Cell.FINISHED_RACK,
)


class TestSpec(Enum):
    E = auto()
    O = auto()
    EO = auto()
    OBAND = auto()
    CBAND = auto()
    OTHER = auto()


TEST_CYCLE: Tuple[TestSpec, ...] = (
    TestSpec.E,
    TestSpec.O,
    TestSpec.EO,
    TestSpec.OBAND,
    TestSpec.CBAND,
    TestSpec.OTHER,
)


def test_label(t: TestSpec) -> str:
    return {
        TestSpec.E: "E",
        TestSpec.O: "O",
        TestSpec.EO: "EO",
        TestSpec.OBAND: "Oband",
        TestSpec.CBAND: "Cband",
        TestSpec.OTHER: "Other",
    }[t]


def default_map() -> List[List[Cell]]:
    g: List[List[Cell]] = [[Cell.FLOOR for _ in range(COLS)] for _ in range(ROWS)]

    for c in range(COLS):
        g[0][c] = Cell.WALL
        g[ROWS - 1][c] = Cell.WALL
    for r in range(ROWS):
        g[r][0] = Cell.WALL
        g[r][COLS - 1] = Cell.WALL

    for c in range(4, 10):
        g[4][c] = Cell.WALL

    g[6][2] = Cell.RECEIVING
    g[6][4] = Cell.PROBER_LOAD
    g[6][5] = Cell.PROBER_WAIT
    g[4][7] = Cell.TEST_BENCH
    g[4][10] = Cell.TEST_CHAMBER
    g[6][12] = Cell.FINISHED_RACK

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
        Cell.RECEIVING,
        Cell.PROBER_LOAD,
        Cell.PROBER_WAIT,
        Cell.TEST_BENCH,
        Cell.TEST_CHAMBER,
        Cell.FINISHED_RACK,
    ):
        return c
    return None


class WaferOrder:
    """One wafer lot with a required test configuration."""

    def __init__(self, recipe: Tuple[Cell, ...], required: TestSpec) -> None:
        self.recipe = recipe
        self.completed_steps: List[Cell] = []
        self.required = required

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

    def force_advance(self, st: Cell) -> bool:
        if self.next_expected() != st:
            return False
        self.completed_steps.append(st)
        return True

    def is_done(self) -> bool:
        return len(self.completed_steps) >= len(self.recipe)

    def progress_text(self) -> str:
        names = {
            Cell.RECEIVING: "Receive",
            Cell.PROBER_LOAD: "Prober load",
            Cell.PROBER_WAIT: "Inventory",
            Cell.TEST_BENCH: "Configure",
            Cell.TEST_CHAMBER: "Test run",
            Cell.FINISHED_RACK: "Finished rack",
        }
        parts: List[str] = []
        for i, step in enumerate(self.recipe):
            label = names[step]
            if i < len(self.completed_steps):
                parts.append(f"[{label}]")
            elif i == len(self.completed_steps):
                parts.append(f"->{label}")
            else:
                parts.append(label)
        return " ".join(parts) + f"  |  target test: {test_label(self.required)}"


def random_test() -> TestSpec:
    return random.choice(TEST_CYCLE)
