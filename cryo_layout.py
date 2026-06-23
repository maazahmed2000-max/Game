"""Cryo lab floor layout — separate from room-temperature prober (dev_layout.json)."""

from __future__ import annotations

import atexit
import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from constants import COLS, ROWS
from dev_layout import (
    LatticeCoord,
    ProberCorners,
    TileCoord,
    Vec2,
    _point_in_convex_quad,
    _replace_with_retry,
    _write_layout_text,
    axis_parallelogram_corners,
    default_play_bounds_corners,
    default_receiving_booths,
    default_tile_axes,
    lattice_cell_at_world,
    lattice_cell_corners,
    lattice_point,
    point_in_lattice_cell,
    snap_to_lattice,
    tiles_from_quad,
)

CRYO_LAYOUT_PATH = Path(__file__).resolve().parent / "cryo_layout.json"

EquipmentSortOutcome = Literal["front", "behind", "strip"]

_cryo_layout: "CryoLayout | None" = None


@dataclass
class CryoLayout:
    play_bounds_corners: ProberCorners = field(default_factory=default_play_bounds_corners)
    receiving_booths: List[TileCoord] = field(default_factory=default_receiving_booths)

    view_anchor_c: float = 13.0
    view_anchor_r: float = 10.0

    tile_origin_c: float = 13.0
    tile_origin_r: float = 10.0
    tile_axis_x: Vec2 = field(default_factory=lambda: default_tile_axes()[0])
    tile_axis_y: Vec2 = field(default_factory=lambda: default_tile_axes()[1])
    blocked_lattice: List[LatticeCoord] = field(default_factory=list)
    lattice_user_defined: bool = False
    blocked_tiles: List[TileCoord] = field(default_factory=list)

    finished_c: int = 22
    finished_r: int = 10

    bond_c: float = 8.5
    bond_r: float = 12.5
    bond_radius: float = 1.35
    bond_front_origin_c: float = 8.5
    bond_front_origin_r: float = 12.5
    bond_front_dx: float = 2.5
    bond_front_dy: float = 2.5
    bond_sort_near_radius: float = 6.0
    bond_sort_side_clear: float = 0.35

    cryostat_c: float = 16.5
    cryostat_r: float = 11.5
    cryostat_radius: float = 1.45
    cryostat_front_origin_c: float = 16.5
    cryostat_front_origin_r: float = 11.5
    cryostat_front_dx: float = 2.5
    cryostat_front_dy: float = 2.5
    cryostat_sort_near_radius: float = 7.0
    cryostat_sort_side_clear: float = 0.35

    def __post_init__(self) -> None:
        self.tile_axis_x = (float(self.tile_axis_x[0]), float(self.tile_axis_x[1]))
        self.tile_axis_y = (float(self.tile_axis_y[0]), float(self.tile_axis_y[1]))
        if not self.blocked_lattice and not self.lattice_user_defined:
            if self.blocked_tiles:
                self._migrate_world_tiles_to_lattice()
            elif not self.blocked_tiles:
                ax, ay = default_tile_axes()
                equip = axis_parallelogram_corners(
                    (self.view_anchor_c, self.view_anchor_r),
                    3.2,
                    2.0,
                    axis_x=ax,
                    axis_y=ay,
                )
                self.blocked_tiles = tiles_from_quad(equip)
                self._migrate_world_tiles_to_lattice()
                self.blocked_tiles = []

    def _migrate_world_tiles_to_lattice(self) -> None:
        origin = self.tile_origin()
        ax, ay = self.tile_axis_x, self.tile_axis_y
        seen: Set[LatticeCoord] = set()
        for c, r in self.blocked_tiles:
            i, j = snap_to_lattice(float(c) + 0.5, float(r) + 0.5, origin, ax, ay)
            if (i, j) not in seen:
                seen.add((i, j))
                self.blocked_lattice.append((i, j))

    def blocked_lattice_set(self) -> Set[LatticeCoord]:
        return {tuple(t) for t in self.blocked_lattice}

    def set_lattice_blocked(self, i: int, j: int, blocked: bool) -> None:
        key = (i, j)
        s = self.blocked_lattice_set()
        if blocked and key not in s:
            self.blocked_lattice.append(key)
        elif not blocked and key in s:
            self.blocked_lattice = [t for t in self.blocked_lattice if t != key]

    def tile_origin(self) -> Vec2:
        return self.tile_origin_c, self.tile_origin_r

    def snap_paint_lattice(self, gc: float, gr: float) -> LatticeCoord:
        return snap_to_lattice(gc, gr, self.tile_origin(), self.tile_axis_x, self.tile_axis_y)

    def lattice_corners(self, i: int, j: int) -> ProberCorners:
        return lattice_cell_corners(i, j, self.tile_origin(), self.tile_axis_x, self.tile_axis_y)

    def cell_at_world(self, gc: float, gr: float) -> LatticeCoord:
        return lattice_cell_at_world(gc, gr, self.tile_origin(), self.tile_axis_x, self.tile_axis_y)

    def cell_contains(self, gc: float, gr: float, i: int, j: int) -> bool:
        return point_in_lattice_cell(
            gc, gr, i, j, self.tile_origin(), self.tile_axis_x, self.tile_axis_y
        )

    def is_cell_walkable(self, i: int, j: int) -> bool:
        return (i, j) not in self.blocked_lattice_set()

    def cell_center(self, i: int, j: int) -> Vec2:
        corners = self.lattice_corners(i, j)
        return (
            sum(p[0] for p in corners) / len(corners),
            sum(p[1] for p in corners) / len(corners),
        )

    def open_at_world(self, gc: float, gr: float) -> bool:
        i, j = self.cell_at_world(gc, gr)
        if not self.is_cell_walkable(i, j):
            return False
        return self.cell_contains(gc, gr, i, j)

    def axis_x_tip(self) -> Vec2:
        ox, oy = self.tile_origin()
        return (ox + self.tile_axis_x[0], oy + self.tile_axis_x[1])

    def axis_y_tip(self) -> Vec2:
        ox, oy = self.tile_origin()
        return (ox + self.tile_axis_y[0], oy + self.tile_axis_y[1])

    def view_anchor(self) -> Vec2:
        return self.view_anchor_c, self.view_anchor_r

    def is_inside_play_bounds(self, col: int, row: int) -> bool:
        return _point_in_convex_quad(col + 0.5, row + 0.5, self.play_bounds_corners)

    def bond_front_origin(self) -> Vec2:
        return self.bond_front_origin_c, self.bond_front_origin_r

    def bond_front_tip(self) -> Vec2:
        return (
            self.bond_front_origin_c + self.bond_front_dx,
            self.bond_front_origin_r + self.bond_front_dy,
        )

    def bond_front_dir(self) -> Vec2:
        fx, fy = self.bond_front_dx, self.bond_front_dy
        ln = math.hypot(fx, fy)
        if ln < 1e-6:
            inv = 1.0 / math.sqrt(2.0)
            return inv, inv
        return fx / ln, fy / ln

    def cryostat_front_origin(self) -> Vec2:
        return self.cryostat_front_origin_c, self.cryostat_front_origin_r

    def cryostat_front_tip(self) -> Vec2:
        return (
            self.cryostat_front_origin_c + self.cryostat_front_dx,
            self.cryostat_front_origin_r + self.cryostat_front_dy,
        )

    def cryostat_front_dir(self) -> Vec2:
        fx, fy = self.cryostat_front_dx, self.cryostat_front_dy
        ln = math.hypot(fx, fy)
        if ln < 1e-6:
            inv = 1.0 / math.sqrt(2.0)
            return inv, inv
        return fx / ln, fy / ln


def _equipment_depth_side(
    origin: Vec2,
    direction: Vec2,
    col: float,
    row: float,
) -> float:
    ox, oy = origin
    fx, fy = direction
    return (col - ox) * fx + (row - oy) * fy


def _equipment_sort_outcome(
    lay: CryoLayout,
    *,
    center_c: float,
    center_r: float,
    origin: Vec2,
    direction: Vec2,
    side_clear: float,
    col: float,
    row: float,
) -> EquipmentSortOutcome:
    side = _equipment_depth_side(origin, direction, col, row)
    if side < -side_clear:
        return "behind"
    if side > side_clear:
        return "front"
    return "strip"


def bond_sort_in_near_zone(col: float, row: float, lay: CryoLayout | None = None) -> bool:
    lay = lay or get_cryo_layout()
    near = lay.bond_sort_near_radius
    return (col - lay.bond_c) ** 2 + (row - lay.bond_r) ** 2 <= near * near


def cryostat_sort_in_near_zone(col: float, row: float, lay: CryoLayout | None = None) -> bool:
    lay = lay or get_cryo_layout()
    near = lay.cryostat_sort_near_radius
    return (col - lay.cryostat_c) ** 2 + (row - lay.cryostat_r) ** 2 <= near * near


def bond_sort_outcome(col: float, row: float, lay: CryoLayout | None = None) -> EquipmentSortOutcome:
    lay = lay or get_cryo_layout()
    return _equipment_sort_outcome(
        lay,
        center_c=lay.bond_c,
        center_r=lay.bond_r,
        origin=lay.bond_front_origin(),
        direction=lay.bond_front_dir(),
        side_clear=lay.bond_sort_side_clear,
        col=col,
        row=row,
    )


def cryostat_sort_outcome(col: float, row: float, lay: CryoLayout | None = None) -> EquipmentSortOutcome:
    lay = lay or get_cryo_layout()
    return _equipment_sort_outcome(
        lay,
        center_c=lay.cryostat_c,
        center_r=lay.cryostat_r,
        origin=lay.cryostat_front_origin(),
        direction=lay.cryostat_front_dir(),
        side_clear=lay.cryostat_sort_side_clear,
        col=col,
        row=row,
    )


def player_draws_in_front_of_bond(
    col: float,
    row: float,
    *,
    player_foot_y: Optional[float] = None,
    bond_foot_y: Optional[float] = None,
    lay: CryoLayout | None = None,
) -> bool:
    lay = lay or get_cryo_layout()
    clear = lay.bond_sort_side_clear
    side = _equipment_depth_side(lay.bond_front_origin(), lay.bond_front_dir(), col, row)
    if side < -clear:
        return False
    if side > clear:
        return True
    if not bond_sort_in_near_zone(col, row, lay):
        return side >= 0.0
    if player_foot_y is None or bond_foot_y is None:
        return side >= 0.0
    return player_foot_y >= bond_foot_y


def player_draws_in_front_of_cryostat(
    col: float,
    row: float,
    *,
    player_foot_y: Optional[float] = None,
    cryo_foot_y: Optional[float] = None,
    lay: CryoLayout | None = None,
) -> bool:
    lay = lay or get_cryo_layout()
    clear = lay.cryostat_sort_side_clear
    side = _equipment_depth_side(lay.cryostat_front_origin(), lay.cryostat_front_dir(), col, row)
    if side < -clear:
        return False
    if side > clear:
        return True
    if not cryostat_sort_in_near_zone(col, row, lay):
        return side >= 0.0
    if player_foot_y is None or cryo_foot_y is None:
        return side >= 0.0
    return player_foot_y >= cryo_foot_y


def default_cryo_layout() -> CryoLayout:
    return CryoLayout()


def load_cryo_layout() -> CryoLayout:
    if not CRYO_LAYOUT_PATH.exists():
        return default_cryo_layout()
    data = json.loads(CRYO_LAYOUT_PATH.read_text(encoding="utf-8"))
    had_bond_front = "bond_front_origin_c" in data
    had_cryo_front = "cryostat_front_origin_c" in data
    lattice_raw = data.pop("blocked_lattice", None)
    lattice_user_defined = bool(data.pop("lattice_user_defined", lattice_raw is not None))
    blocked_raw = data.pop("blocked_tiles", None)
    blocked: List[TileCoord] = []
    lattice: List[LatticeCoord] = []
    if lattice_raw is not None:
        lattice = [(int(i), int(j)) for i, j in lattice_raw]
        lattice_user_defined = True
    elif blocked_raw is not None:
        blocked = [(int(c), int(r)) for c, r in blocked_raw]

    booths_raw = data.pop("receiving_booths", None)
    receiving_booths = default_receiving_booths()
    if booths_raw is not None:
        receiving_booths = [(int(c), int(r)) for c, r in booths_raw]

    play_raw = data.pop("play_bounds_corners", None)
    if play_raw is None:
        play_bounds_corners = default_play_bounds_corners()
    else:
        play_bounds_corners = [(float(c), float(r)) for c, r in play_raw]

    lay = CryoLayout(
        receiving_booths=receiving_booths,
        blocked_lattice=lattice,
        lattice_user_defined=lattice_user_defined,
        blocked_tiles=blocked,
        play_bounds_corners=play_bounds_corners,
        tile_axis_x=tuple(data.pop("tile_axis_x", default_tile_axes()[0])),  # type: ignore[arg-type]
        tile_axis_y=tuple(data.pop("tile_axis_y", default_tile_axes()[1])),  # type: ignore[arg-type]
        **data,
    )
    if not had_bond_front:
        lay.bond_front_origin_c = lay.bond_c
        lay.bond_front_origin_r = lay.bond_r
    if not had_cryo_front:
        lay.cryostat_front_origin_c = lay.cryostat_c
        lay.cryostat_front_origin_r = lay.cryostat_r
    return lay


def save_cryo_layout(layout: CryoLayout) -> bool:
    payload: Dict[str, Any] = asdict(layout)
    payload["blocked_lattice"] = [[i, j] for i, j in layout.blocked_lattice]
    payload["lattice_user_defined"] = layout.lattice_user_defined
    payload["receiving_booths"] = [[c, r] for c, r in layout.receiving_booths]
    payload["play_bounds_corners"] = [list(p) for p in layout.play_bounds_corners]
    payload.pop("blocked_tiles", None)
    payload["tile_axis_x"] = list(layout.tile_axis_x)
    payload["tile_axis_y"] = list(layout.tile_axis_y)
    text = json.dumps(payload, indent=2)
    tmp = CRYO_LAYOUT_PATH.with_suffix(".json.tmp")
    try:
        _write_layout_text(tmp, text)
    except OSError:
        return False

    if _replace_with_retry(tmp, CRYO_LAYOUT_PATH):
        return True

    try:
        _write_layout_text(CRYO_LAYOUT_PATH, text)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return True
    except OSError:
        pass
    return False


def get_cryo_layout() -> CryoLayout:
    global _cryo_layout
    if _cryo_layout is None:
        _cryo_layout = load_cryo_layout() if CRYO_LAYOUT_PATH.exists() else default_cryo_layout()
    return _cryo_layout


def reload_cryo_layout() -> CryoLayout:
    global _cryo_layout
    _cryo_layout = load_cryo_layout()
    return _cryo_layout


def apply_cryo_layout(layout: CryoLayout) -> None:
    global _cryo_layout
    _cryo_layout = layout


def commit_cryo_layout(layout: CryoLayout) -> bool:
    if layout.blocked_lattice:
        layout.lattice_user_defined = True
    apply_cryo_layout(layout)
    return save_cryo_layout(layout)


def flush_cryo_layout_to_disk() -> None:
    lay = _cryo_layout
    if lay is not None:
        try:
            save_cryo_layout(lay)
        except OSError:
            pass


def apply_cryo_anchor_drag(lay: CryoLayout, start: CryoLayout, dc: float, dr: float) -> None:
    """Drag camera anchor — move floor tiles and stations together."""
    lay.view_anchor_c = start.view_anchor_c + dc
    lay.view_anchor_r = start.view_anchor_r + dr
    lay.tile_origin_c = start.tile_origin_c + dc
    lay.tile_origin_r = start.tile_origin_r + dr

    from dev_layout import nudge_corners

    lay.play_bounds_corners = nudge_corners(start.play_bounds_corners, dc, dr)
    lay.finished_c = max(0, min(COLS - 1, int(round(start.finished_c + dc))))
    lay.finished_r = max(0, min(ROWS - 1, int(round(start.finished_r + dr))))
    lay.bond_c = start.bond_c + dc
    lay.bond_r = start.bond_r + dr
    lay.bond_front_origin_c = start.bond_front_origin_c + dc
    lay.bond_front_origin_r = start.bond_front_origin_r + dr
    lay.cryostat_c = start.cryostat_c + dc
    lay.cryostat_r = start.cryostat_r + dr
    lay.cryostat_front_origin_c = start.cryostat_front_origin_c + dc
    lay.cryostat_front_origin_r = start.cryostat_front_origin_r + dr

    lay.receiving_booths = [
        (
            max(0, min(COLS - 1, int(round(c + dc)))),
            max(0, min(ROWS - 1, int(round(r + dr)))),
        )
        for c, r in start.receiving_booths
    ]


atexit.register(flush_cryo_layout_to_disk)
