"""PSI Quantum–style wafer test floor: stations, wafer orders, and test recipes."""

from __future__ import annotations

import random
from dataclasses import dataclass
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


def receiving_booths() -> List[Tuple[int, int]]:
    """Pickup tiles in front of the STORAGE unit (left bay on the background)."""
    return [(5, 9), (5, 10), (5, 11), (6, 9), (6, 10)]


def prober_visual_center() -> Tuple[float, float]:
    """Screen placement for the prober cluster — center of the open floor."""
    return (13.0, 10.0)


@dataclass(frozen=True)
class StationZone:
    """Interaction hitbox aligned to prober cluster art (offsets from center)."""

    zone_id: str
    col: float
    row: float
    step: Cell
    radius: float = 1.35


def _zone(col_off: float, row_off: float, step: Cell, zone_id: str, radius: float = 1.35) -> StationZone:
    cx, cy = prober_visual_center()
    return StationZone(zone_id, cx + col_off, cy + row_off, step, radius)


def prober_station_zones() -> Tuple[StationZone, ...]:
    """Hitboxes: MHU center, side racks (config), chucks (test), load pads."""
    return (
        _zone(0.0, 0.0, Cell.PROBER_WAIT, "mhu", 2.0),
        _zone(-1.75, -0.95, Cell.TEST_BENCH, "rack_l", 1.25),
        _zone(1.75, -0.95, Cell.TEST_BENCH, "rack_r", 1.25),
        _zone(-2.05, 0.05, Cell.TEST_CHAMBER, "chuck_l", 1.3),
        _zone(2.05, 0.05, Cell.TEST_CHAMBER, "chuck_r", 1.3),
        _zone(-2.05, 0.75, Cell.PROBER_LOAD, "load_l", 1.25),
        _zone(2.05, 0.75, Cell.PROBER_LOAD, "load_r", 1.25),
    )


def config_rack_zones() -> List[StationZone]:
    return [z for z in prober_station_zones() if z.step == Cell.TEST_BENCH]


def mhu_zone() -> StationZone:
    return prober_station_zones()[0]


def mhu_tile() -> Tuple[int, int]:
    z = mhu_zone()
    return int(round(z.col)), int(round(z.row))


def prober_chuck_zones() -> List[StationZone]:
    return [z for z in prober_station_zones() if z.step == Cell.TEST_CHAMBER]


def prober_chuck_tiles() -> List[Tuple[int, int]]:
    return [(int(round(z.col)), int(round(z.row))) for z in prober_chuck_zones()]


def config_rack_tiles() -> List[Tuple[int, int]]:
    return [(int(round(z.col)), int(round(z.row))) for z in config_rack_zones()]


# How close (in grid units) the operator can stand to interact with a station.
INTERACT_RADIUS = 1.55


def in_vicinity(
    col: float,
    row: float,
    target: Tuple[int, int],
    radius: float = INTERACT_RADIUS,
) -> bool:
    tc, tr = target
    return (col - tc) ** 2 + (row - tr) ** 2 <= radius * radius


def in_vicinity_of_station(
    cells: List[List[Cell]],
    col: float,
    row: float,
    kind: Cell,
    radius: float = INTERACT_RADIUS,
) -> bool:
    for c, r in all_station_tiles(cells, kind):
        if in_vicinity(col, row, (c, r), radius):
            return True
    return False


def near_zone(col: float, row: float, zone: StationZone) -> bool:
    return (col - zone.col) ** 2 + (row - zone.row) ** 2 <= zone.radius * zone.radius


def near_mhu(col: float, row: float, radius: float = INTERACT_RADIUS) -> bool:
    z = mhu_zone()
    return near_zone(col, row, z) if radius >= z.radius else in_vicinity(col, row, mhu_tile(), radius)


def near_step_zone(col: float, row: float, step: Cell) -> bool:
    for z in prober_station_zones():
        if z.step == step and near_zone(col, row, z):
            return True
    return False


def player_near_step(
    cells: List[List[Cell]],
    col: float,
    row: float,
    order: WaferOrder,
    step: Cell,
    radius: float = INTERACT_RADIUS,
) -> bool:
    del radius  # zones carry their own radius
    if step == Cell.RECEIVING:
        return in_vicinity(col, row, order.spawn_booth)
    if step in (Cell.PROBER_WAIT, Cell.PROBER_LOAD, Cell.TEST_BENCH, Cell.TEST_CHAMBER):
        return near_step_zone(col, row, step)
    return in_vicinity_of_station(cells, col, row, step)


def _storage_blocked(col: int, row: int) -> bool:
    """STORAGE shelving — not walkable through the rack."""
    return col <= 9 and row <= 8


def _prober_footprint_blocked(col: int, row: int) -> bool:
    """Iso-aligned rectangle under the TEL cluster (clean edges on the tile grid)."""
    cx, cy = prober_visual_center()
    u = col - row
    v = col + row
    cu = cx - cy
    cv = cx + cy
    half_u = 4.6
    half_v = 2.1
    return abs(u - cu) <= half_u and abs(v - cv) <= half_v


def find_walkable_spawn(cells: List[List[Cell]]) -> Tuple[float, float]:
    """Spawn in front of the prober, never inside its footprint."""
    cx, cy = prober_visual_center()
    for c, r in (
        (cx + 1.5, cy + 2.2),
        (cx + 2.0, cy + 1.8),
        (cx, cy + 2.8),
        (cx - 1.0, cy + 2.5),
        (cx + 1.0, cy + 3.0),
        (10.0, 12.0),
        (16.0, 11.0),
    ):
        ic, ir = int(round(c)), int(round(r))
        if walkable(cells, ic, ir):
            return c, r
    for r in range(ROWS):
        for c in range(COLS):
            if walkable(cells, c, r):
                return float(c) + 0.5, float(r) + 0.5
    return 14.0, 12.0


def _blocked_by_background(col: int, row: int) -> bool:
    """Walls, storage rack, prober body, and right-side cabinet."""
    if col <= 2 or col >= COLS - 3:
        return True
    if row <= 2 or row >= ROWS - 3:
        return True
    if _storage_blocked(col, row):
        return True
    if _prober_footprint_blocked(col, row):
        return True
    # SPADE tool cabinet (upper-right)
    if col >= 22 and row <= 8:
        return True
    return False


def default_map() -> List[List[Cell]]:
    g: List[List[Cell]] = [[Cell.WALL for _ in range(COLS)] for _ in range(ROWS)]

    for r in range(ROWS):
        for c in range(COLS):
            if not _blocked_by_background(c, r):
                g[r][c] = Cell.FLOOR

    for c, r in receiving_booths():
        g[r][c] = Cell.RECEIVING

    # Prober uses zone hitboxes only (footprint tiles stay WALL); no grid cells on the sprite
    g[10][22] = Cell.FINISHED_RACK

    return g


def step_destination(
    cells: List[List[Cell]],
    order: WaferOrder,
    *,
    carrying: bool,
) -> Optional[Tuple[int, int]]:
    """Grid tile the player should head to for the current recipe step."""
    exp = order.next_expected()
    if exp is None:
        return None
    if exp == Cell.RECEIVING:
        return order.spawn_booth if not carrying else None
    if exp in (Cell.PROBER_WAIT, Cell.PROBER_LOAD, Cell.TEST_BENCH, Cell.TEST_CHAMBER):
        for z in prober_station_zones():
            if z.step == exp:
                return int(round(z.col)), int(round(z.row))
    if exp == Cell.FINISHED_RACK:
        tiles = all_station_tiles(cells, exp)
        return tiles[0] if tiles else None
    return None


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
            Cell.PROBER_WAIT: "MHU inventory",
            Cell.TEST_BENCH: "Config rack",
            Cell.TEST_CHAMBER: "Prober test",
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
