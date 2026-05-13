"""PSI Quantum–style wafer test floor: stations, wafer orders, and test recipes."""

from __future__ import annotations

import random
from enum import Enum, auto
from typing import List, Optional, Tuple

from constants import COLS, ROWS


class Cell(Enum):
    FLOOR = auto()
    WALL = auto()
    RECEIVING = auto()
    PROBER_LOAD = auto()
    PROBER_WAIT = auto()
    TEST_BENCH = auto()
    TEST_CHAMBER = auto()
    FINISHED_RACK = auto()


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


# Five incoming booths (left bay) — matches floor-plan “column of small rooms”
def receiving_booths() -> List[Tuple[int, int]]:
    return [(3, 4), (3, 5), (3, 6), (3, 7), (3, 8)]


def default_map() -> List[List[Cell]]:
    g: List[List[Cell]] = [[Cell.FLOOR for _ in range(COLS)] for _ in range(ROWS)]

    for c in range(COLS):
        g[0][c] = Cell.WALL
        g[ROWS - 1][c] = Cell.WALL
    for r in range(ROWS):
        g[r][0] = Cell.WALL
        g[r][COLS - 1] = Cell.WALL

    for c, r in receiving_booths():
        g[r][c] = Cell.RECEIVING

    # Open central floor — stations along main run (no interior walls)
    g[6][10] = Cell.PROBER_LOAD
    g[6][12] = Cell.PROBER_WAIT
    g[5][16] = Cell.TEST_BENCH
    g[5][20] = Cell.TEST_CHAMBER
    g[6][24] = Cell.FINISHED_RACK

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


def all_station_tiles(cells: List[List[Cell]], kind: Cell) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for r in range(ROWS):
        for c in range(COLS):
            if cells[r][c] == kind:
                out.append((c, r))
    return out


class WaferOrder:
    """One wafer lot; pickup only at the randomly assigned receiving booth for this lot."""

    def __init__(self, recipe: Tuple[Cell, ...], required: TestSpec, spawn_booth: Tuple[int, int]) -> None:
        self.recipe = recipe
        self.completed_steps: List[Cell] = []
        self.required = required
        self.spawn_booth = spawn_booth

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
        bx, by = self.spawn_booth
        return (
            " ".join(parts)
            + f"  |  target test: {test_label(self.required)}  |  pickup booth ({bx},{by})"
        )


def random_test() -> TestSpec:
    return random.choice(TEST_CYCLE)


def random_spawn_booth() -> Tuple[int, int]:
    return random.choice(receiving_booths())
