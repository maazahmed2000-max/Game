"""PSI Quantum–style wafer test floor: stations, wafer orders, and test recipes."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Literal, Optional, Tuple

ProberSortOutcome = Literal["front", "behind", "strip"]
ProberSide = Literal["l", "r"]

from constants import (
    CHAMBER_RUN_MAX_S,
    CHAMBER_RUN_MIN_S,
    CHUCK_STANDBY_NOTICE_S,
    CHUCK_STANDBY_PENALTY_INTERVAL_S,
    CHUCK_STANDBY_PENALTY_S,
    COLS,
    ROWS,
)
from dev_layout import ZoneDef, get_layout, lattice_cell_corners, point_in_lattice_cell


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


class ChuckStatus(Enum):
    PRODUCTIVE = auto()
    STANDBY = auto()


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
    """Pickup tiles where incoming wafer lots spawn (editable in map editor)."""
    return list(get_layout().receiving_booths)


def prober_visual_center() -> Tuple[float, float]:
    """World position of the prober cluster (zones are offset from here)."""
    lay = get_layout()
    return lay.prober_cx, lay.prober_cy


def layout_camera_anchor() -> Tuple[float, float]:
    """World point pinned to screen center — fixed so prober can move on the floor after reload."""
    lay = get_layout()
    return lay.view_anchor()


def player_prober_depth_side(col: float, row: float) -> float:
    """Signed side of the prober front plane: >0 in front, <0 behind (for sprite sort)."""
    lay = get_layout()
    fx, fy = lay.prober_front_dir()
    ox, oy = lay.prober_front_origin()
    return (col - ox) * fx + (row - oy) * fy


def prober_sort_near_radius() -> float:
    return get_layout().prober_sort_near_radius


def prober_sort_side_clear() -> float:
    return get_layout().prober_sort_side_clear


def prober_sort_in_near_zone(col: float, row: float) -> bool:
    lay = get_layout()
    pc, pr = lay.prober_cx, lay.prober_cy
    near = lay.prober_sort_near_radius
    return (col - pc) ** 2 + (row - pr) ** 2 <= near * near


def prober_sort_outcome(col: float, row: float) -> ProberSortOutcome:
    """How the operator sorts vs the prober at this floor position (matches in-game rules)."""
    clear = prober_sort_side_clear()
    side = player_prober_depth_side(col, row)
    if side < -clear:
        return "behind"
    if side > clear:
        return "front"
    return "strip"


def player_draws_in_front_of_prober(
    col: float,
    row: float,
    *,
    player_foot_y: Optional[float] = None,
    prober_foot_y: Optional[float] = None,
) -> bool:
    """True when the operator sprite should draw on top of the prober cluster."""
    clear = prober_sort_side_clear()
    side = player_prober_depth_side(col, row)
    if side < -clear:
        return False
    if side > clear:
        return True
    if not prober_sort_in_near_zone(col, row):
        return side >= 0.0
    if player_foot_y is None or prober_foot_y is None:
        return side >= 0.0
    return player_foot_y >= prober_foot_y


@dataclass(frozen=True)
class StationZone:
    """Interaction hitbox aligned to prober cluster art (offsets from center)."""

    zone_id: str
    col: float
    row: float
    step: Cell
    radius: float = 1.35


def _zone_from_def(zone_id: str, zd: ZoneDef) -> StationZone:
    cx, cy = prober_visual_center()
    step = Cell[zd.step] if zd.step in Cell.__members__ else Cell.PROBER_WAIT
    return StationZone(zone_id, cx + zd.dx, cy + zd.dy, step, zd.radius)


def prober_station_zones() -> Tuple[StationZone, ...]:
    """Hitboxes: MHU center, side racks (config), chucks (test), load pads."""
    lay = get_layout()
    return tuple(_zone_from_def(zid, zd) for zid, zd in lay.zones.items())


def config_rack_zones() -> List[StationZone]:
    return [z for z in prober_station_zones() if z.step == Cell.TEST_BENCH]


def mhu_zone() -> StationZone:
    for z in prober_station_zones():
        if z.zone_id == "mhu":
            return z
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


def zone_by_id(zone_id: str) -> Optional[StationZone]:
    for z in prober_station_zones():
        if z.zone_id == zone_id:
            return z
    return None


def player_near_zone_id(col: float, row: float, zone_id: str) -> bool:
    z = zone_by_id(zone_id)
    return z is not None and near_zone(col, row, z)


def nearest_prober_side(col: float, row: float, prefix: str) -> ProberSide:
    """Nearest left/right station for load, rack, or chuck."""
    zl = zone_by_id(f"{prefix}_l")
    zr = zone_by_id(f"{prefix}_r")
    if zl is None and zr is None:
        return "l"
    if zl is None:
        return "r"
    if zr is None:
        return "l"
    dl = (col - zl.col) ** 2 + (row - zl.row) ** 2
    dr = (col - zr.col) ** 2 + (row - zr.row) ** 2
    return "l" if dl <= dr else "r"


def nearest_rack_side(col: float, row: float) -> Optional[ProberSide]:
    if not (player_near_zone_id(col, row, "rack_l") or player_near_zone_id(col, row, "rack_r")):
        return None
    return nearest_prober_side(col, row, "rack")


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
    order: "WaferOrder",
    step: Cell,
    radius: float = INTERACT_RADIUS,
) -> bool:
    del radius
    if step == Cell.RECEIVING:
        return in_vicinity(col, row, order.spawn_booth)
    if step == Cell.PROBER_WAIT:
        return near_mhu(col, row)
    side = order.prober_side
    if step == Cell.PROBER_LOAD:
        if side:
            return player_near_zone_id(col, row, f"load_{side}")
        return near_step_zone(col, row, step)
    if step == Cell.TEST_BENCH:
        if side:
            return player_near_zone_id(col, row, f"rack_{side}")
        return player_near_zone_id(col, row, "rack_l") or player_near_zone_id(col, row, "rack_r")
    if step == Cell.TEST_CHAMBER:
        if side:
            return player_near_zone_id(col, row, f"chuck_{side}")
        return player_near_zone_id(col, row, "chuck_l") or player_near_zone_id(col, row, "chuck_r")
    if step == Cell.FINISHED_RACK:
        return in_vicinity_of_station(cells, col, row, step)
    return in_vicinity_of_station(cells, col, row, step)


def _storage_blocked(col: int, row: int) -> bool:
    """STORAGE shelving — not walkable through the rack."""
    lay = get_layout()
    return col <= lay.storage_c1 and row <= lay.storage_r1


def _structural_blocked(col: int, row: int) -> bool:
    """Fixed map geometry (walls, storage, spade) — not the painted skew lattice."""
    lay = get_layout()
    if col <= lay.wall_left or col >= lay.wall_right:
        return True
    if row <= lay.wall_top or row >= lay.wall_bottom:
        return True
    if _storage_blocked(col, row):
        return True
    if col >= lay.spade_c0 and row <= lay.spade_r1:
        return True
    return False


_STATION_CELLS = frozenset(
    {
        Cell.RECEIVING,
        Cell.PROBER_LOAD,
        Cell.PROBER_WAIT,
        Cell.TEST_BENCH,
        Cell.TEST_CHAMBER,
        Cell.FINISHED_RACK,
    }
)


def _apply_lattice_floor(cells: List[List[Cell]]) -> None:
    """Build walkable map from skew-lattice parallelograms (axes + paint define real tiles)."""
    lay = get_layout()
    origin = lay.tile_origin()
    ax, ay = lay.tile_axis_x, lay.tile_axis_y

    for r in range(ROWS):
        for c in range(COLS):
            if cells[r][c] in _STATION_CELLS:
                continue
            cells[r][c] = Cell.WALL

    for i in range(-32, 33):
        for j in range(-32, 33):
            corners = lattice_cell_corners(i, j, origin, ax, ay)
            cols = [p[0] for p in corners]
            rows = [p[1] for p in corners]
            c0 = max(0, int(math.floor(min(cols))))
            c1 = min(COLS - 1, int(math.ceil(max(cols))))
            r0 = max(0, int(math.floor(min(rows))))
            r1 = min(ROWS - 1, int(math.ceil(max(rows))))
            open_cell = lay.is_cell_walkable(i, j)
            for c in range(c0, c1 + 1):
                for r in range(r0, r1 + 1):
                    if cells[r][c] in _STATION_CELLS:
                        continue
                    if _structural_blocked(c, r):
                        continue
                    if not point_in_lattice_cell(
                        float(c) + 0.5, float(r) + 0.5, i, j, origin, ax, ay
                    ):
                        continue
                    cells[r][c] = Cell.FLOOR if open_cell else Cell.WALL


def world_walkable(cells: List[List[Cell]], col: float, row: float) -> bool:
    """Walk hitbox = inside an open skew-lattice parallelogram (axes define tile shape)."""
    gc, gr = float(col), float(row)
    ic, ir = int(round(gc)), int(round(gr))
    if not (0 <= ic < COLS and 0 <= ir < ROWS):
        return False
    if _structural_blocked(ic, ir):
        return False
    if cells[ir][ic] in _STATION_CELLS:
        return True
    return get_layout().open_at_world(gc, gr)


def find_walkable_spawn(cells: List[List[Cell]]) -> Tuple[float, float]:
    """Spawn at the center of an open skew-lattice cell near the prober."""
    lay = get_layout()
    cx, cy = prober_visual_center()
    i0, j0 = lay.cell_at_world(cx, cy)
    for radius in range(0, 14):
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                if abs(di) != radius and abs(dj) != radius and radius > 0:
                    continue
                i, j = i0 + di, j0 + dj
                if not lay.is_cell_walkable(i, j):
                    continue
                wc, wr = lay.cell_center(i, j)
                if world_walkable(cells, wc, wr):
                    return wc, wr
    for r in range(ROWS):
        for c in range(COLS):
            if world_walkable(cells, float(c) + 0.5, float(r) + 0.5):
                return float(c) + 0.5, float(r) + 0.5
    return 14.0, 12.0


def default_map() -> List[List[Cell]]:
    g: List[List[Cell]] = [[Cell.WALL for _ in range(COLS)] for _ in range(ROWS)]

    for c, r in receiving_booths():
        g[r][c] = Cell.RECEIVING

    lay = get_layout()
    g[lay.finished_r][lay.finished_c] = Cell.FINISHED_RACK

    _apply_lattice_floor(g)
    return g


def refresh_map_from_layout() -> List[List[Cell]]:
    """Rebuild walkable grid after dev layout edits."""
    return default_map()


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
    side = order.prober_side
    if exp == Cell.PROBER_WAIT:
        z = mhu_zone()
        return int(round(z.col)), int(round(z.row))
    if exp == Cell.PROBER_LOAD and side:
        z = zone_by_id(f"load_{side}")
        if z:
            return int(round(z.col)), int(round(z.row))
    if exp == Cell.TEST_BENCH and side:
        z = zone_by_id(f"rack_{side}")
        if z:
            return int(round(z.col)), int(round(z.row))
    if exp == Cell.TEST_CHAMBER and side:
        z = zone_by_id(f"chuck_{side}")
        if z:
            return int(round(z.col)), int(round(z.row))
    if exp in (Cell.PROBER_LOAD, Cell.TEST_BENCH, Cell.TEST_CHAMBER):
        for z in prober_station_zones():
            if z.step == exp:
                return int(round(z.col)), int(round(z.row))
    if exp == Cell.FINISHED_RACK:
        if not carrying:
            if side:
                z = zone_by_id(f"load_{side}")
                if z:
                    return int(round(z.col)), int(round(z.row))
            for z in prober_station_zones():
                if z.step == Cell.PROBER_LOAD:
                    return int(round(z.col)), int(round(z.row))
        tiles = all_station_tiles(cells, exp)
        return tiles[0] if tiles else None
    return None


def walkable(cells: List[List[Cell]], col: float, row: float) -> bool:
    return world_walkable(cells, col, row)


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
        self.chamber_duration = 0.0
        self.chamber_elapsed = 0.0
        self.chamber_started = False
        self.prober_side: Optional[ProberSide] = None

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

    def ticket_label(self) -> str:
        """Final lot type only (Overcooked-style ticket, not recipe steps)."""
        return test_label(self.required)

    def start_chamber_run(self) -> None:
        if self.next_expected() != Cell.TEST_CHAMBER or self.chamber_started:
            return
        if self.prober_side is None:
            return
        self.chamber_started = True
        self.chamber_elapsed = 0.0
        self.chamber_duration = random.uniform(CHAMBER_RUN_MIN_S, CHAMBER_RUN_MAX_S)

    def tick_chamber(self, dt: float) -> bool:
        """Advance chamber timer; returns True when the run completes."""
        if not self.chamber_started or self.next_expected() != Cell.TEST_CHAMBER:
            return False
        self.chamber_elapsed += dt
        if self.chamber_elapsed >= self.chamber_duration:
            self.force_advance(Cell.TEST_CHAMBER)
            self.chamber_started = False
            return True
        return False

    def chamber_progress(self) -> float:
        if not self.chamber_started or self.chamber_duration <= 0:
            return 0.0
        return min(1.0, self.chamber_elapsed / self.chamber_duration)


def wafer_visible_on_operator(order: "WaferOrder") -> bool:
    """Show carried wafer sprite only when the lot is in the operator's hands."""
    exp = order.next_expected()
    return exp in (Cell.PROBER_LOAD, Cell.FINISHED_RACK)


def chamber_order_on_side(orders: List["WaferOrder"], side: ProberSide) -> Optional["WaferOrder"]:
    for o in orders:
        if o.chamber_started and o.prober_side == side:
            return o
    return None


def chuck_status_for_side(orders: List["WaferOrder"], side: ProberSide) -> ChuckStatus:
    """Green productive while a wafer is in chamber test; yellow standby otherwise."""
    if chamber_order_on_side(orders, side) is not None:
        return ChuckStatus.PRODUCTIVE
    return ChuckStatus.STANDBY


@dataclass
class StandbyPenaltyNotice:
    side: ProberSide
    amount_s: float
    time_left: float = CHUCK_STANDBY_NOTICE_S


@dataclass
class ChuckStandbyTracker:
    """Tracks idle time per chuck and applies shift-timer penalties."""

    elapsed: dict[str, float] = field(default_factory=lambda: {"l": 0.0, "r": 0.0})
    penalty_blocks: dict[str, int] = field(default_factory=lambda: {"l": 0, "r": 0})
    armed: bool = False
    notices: List[StandbyPenaltyNotice] = field(default_factory=list)

    def tick(self, orders: List["WaferOrder"], dt: float) -> float:
        """Advance standby timers; return extra seconds to deduct from the shift."""
        self._decay_notices(dt)
        if orders and not self.armed:
            self.armed = True
        if not self.armed:
            return 0.0

        total = 0.0
        for side in ("l", "r"):
            if chuck_status_for_side(orders, side) == ChuckStatus.PRODUCTIVE:
                self.elapsed[side] = 0.0
                self.penalty_blocks[side] = 0
                continue
            self.elapsed[side] += dt
            blocks = int(self.elapsed[side] // CHUCK_STANDBY_PENALTY_INTERVAL_S)
            new_blocks = blocks - self.penalty_blocks[side]
            if new_blocks > 0:
                total += new_blocks * CHUCK_STANDBY_PENALTY_S
                self.penalty_blocks[side] = blocks
                self.notices.append(
                    StandbyPenaltyNotice(
                        side=side,
                        amount_s=new_blocks * CHUCK_STANDBY_PENALTY_S,
                    )
                )
        return total

    def _decay_notices(self, dt: float) -> None:
        alive: List[StandbyPenaltyNotice] = []
        for notice in self.notices:
            notice.time_left -= dt
            if notice.time_left > 0:
                alive.append(notice)
        self.notices = alive

    def seconds_to_penalty(self, side: ProberSide) -> float:
        """Seconds until the next standby penalty tick."""
        if not self.armed:
            return CHUCK_STANDBY_PENALTY_INTERVAL_S
        e = self.elapsed.get(side, 0.0)
        if e < CHUCK_STANDBY_PENALTY_INTERVAL_S:
            return CHUCK_STANDBY_PENALTY_INTERVAL_S - e
        rem = e % CHUCK_STANDBY_PENALTY_INTERVAL_S
        return 0.0 if rem == 0.0 else CHUCK_STANDBY_PENALTY_INTERVAL_S - rem


def bench_order_on_side(
    orders: List["WaferOrder"],
    side: ProberSide,
    col: float,
    row: float,
) -> Optional["WaferOrder"]:
    if not player_near_zone_id(col, row, f"rack_{side}"):
        return None
    for o in orders:
        if o.next_expected() == Cell.TEST_BENCH and o.prober_side == side:
            return o
    for o in orders:
        if o.next_expected() == Cell.TEST_BENCH:
            return o
    return None


def gameplay_focus_order(
    orders: List["WaferOrder"],
    carrying_idx: Optional[int],
    cells: List[List[Cell]],
    col: float,
    row: float,
) -> Optional["WaferOrder"]:
    """Order the HUD / objective should emphasize (not background chamber runs)."""
    if carrying_idx is not None and 0 <= carrying_idx < len(orders):
        return orders[carrying_idx]
    for o in orders:
        exp = o.next_expected()
        if exp is None:
            continue
        if exp == Cell.TEST_CHAMBER and o.chamber_started:
            continue
        if player_near_step(cells, col, row, o, exp):
            return o
    for o in orders:
        exp = o.next_expected()
        if exp is None:
            continue
        if exp == Cell.TEST_CHAMBER and o.chamber_started:
            continue
        return o
    return orders[0] if orders else None


def orders_queue_text(orders: List["WaferOrder"]) -> str:
    """Comma-separated final test types queued — current lot first."""
    if not orders:
        return "Queue: —"
    parts: List[str] = []
    for i, order in enumerate(orders):
        tag = order.ticket_label()
        parts.append(f"▸ {tag}" if i == 0 else tag)
    return "Queue:  " + "   ".join(parts)


def random_test() -> TestSpec:
    return random.choice(TEST_CYCLE)


def random_spawn_booth() -> Tuple[int, int]:
    return random.choice(receiving_booths())
