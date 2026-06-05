"""Dev-only floor layout (walls, blocks, zones). Not used when DEBUG_MAP_EDITOR is False."""

from __future__ import annotations

import atexit
import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from constants import COLS, ROWS

LAYOUT_PATH = Path(__file__).resolve().parent / "dev_layout.json"

TileCoord = Tuple[int, int]
LatticeCoord = Tuple[int, int]
# Legacy parallelogram corners (col, row), CCW — used only to migrate old saves.
ProberCorners = List[Tuple[float, float]]


def _point_in_convex_quad(px: float, py: float, corners: ProberCorners) -> bool:
    if len(corners) < 3:
        return False

    def cross(ox: float, oy: float, ax: float, ay: float, bx: float, by: float) -> float:
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

    signs = [
        cross(corners[i][0], corners[i][1], corners[(i + 1) % len(corners)][0], corners[(i + 1) % len(corners)][1], px, py) >= 0
        for i in range(len(corners))
    ]
    return all(signs) or not any(signs)


def tiles_from_quad(corners: ProberCorners) -> List[TileCoord]:
    """Rasterize a parallelogram into integer floor tiles."""
    if not corners:
        return []
    cols = [c for c, _ in corners]
    rows = [r for _, r in corners]
    c0, c1 = int(math.floor(min(cols))), int(math.ceil(max(cols)))
    r0, r1 = int(math.floor(min(rows))), int(math.ceil(max(rows)))
    out: List[TileCoord] = []
    for c in range(max(0, c0), min(COLS, c1 + 1)):
        for r in range(max(0, r0), min(ROWS, r1 + 1)):
            if _point_in_convex_quad(c + 0.5, r + 0.5, corners):
                out.append((c, r))
    return out


def prober_corners_from_legacy(
    cx: float = 13.0,
    cy: float = 10.0,
    half_u: float = 4.6,
    half_v: float = 2.1,
) -> ProberCorners:
    """Build default parallelogram from old center + iso half-extents."""
    cu, cv = cx - cy, cx + cy
    out: ProberCorners = []
    for du, dv in ((half_u, half_v), (-half_u, half_v), (-half_u, -half_v), (half_u, -half_v)):
        u, v = cu + du, cv + dv
        out.append(((u + v) * 0.5, (v - u) * 0.5))
    return out


def default_prober_corners() -> ProberCorners:
    return prober_corners_from_legacy()


def default_receiving_booths() -> List[TileCoord]:
    return [(5, 9), (5, 10), (5, 11), (6, 9), (6, 10)]


Vec2 = Tuple[float, float]


def default_tile_axes() -> Tuple[Vec2, Vec2]:
    """Default X/Y step along isometric diamond edges (matches typical prober angle)."""
    return (1.0, 1.0), (1.0, -1.0)


def axis_parallelogram_corners(
    center: Vec2,
    half_i: float,
    half_j: float,
    *,
    axis_x: Vec2,
    axis_y: Vec2,
) -> ProberCorners:
    """CCW parallelogram aligned to the skew tile axes."""
    return [
        lattice_point(center, axis_x, axis_y, -half_i, -half_j),
        lattice_point(center, axis_x, axis_y, half_i, -half_j),
        lattice_point(center, axis_x, axis_y, half_i, half_j),
        lattice_point(center, axis_x, axis_y, -half_i, half_j),
    ]


def rect_to_corners(wl: float, wt: float, wr: float, wb: float) -> ProberCorners:
    return [(wl, wt), (wr, wt), (wr, wb), (wl, wb)]


def nudge_corners(corners: ProberCorners, dc: float, dr: float) -> ProberCorners:
    return [(c + dc, r + dr) for c, r in corners]


def default_play_bounds_corners() -> ProberCorners:
    ax, ay = default_tile_axes()
    return axis_parallelogram_corners((13.0, 10.0), 8.0, 5.0, axis_x=ax, axis_y=ay)


def default_storage_corners() -> ProberCorners:
    ax, ay = default_tile_axes()
    return axis_parallelogram_corners((13.0, 10.0), 4.0, 4.0, axis_x=ax, axis_y=ay)


def snap_to_lattice(
    gc: float,
    gr: float,
    origin: Vec2,
    axis_x: Vec2,
    axis_y: Vec2,
) -> LatticeCoord:
    """Nearest skew-lattice indices (i, j) for a world position — O(1)."""
    ox, oy = origin
    vx, vy = axis_x, axis_y
    px, py = gc - ox, gr - oy
    det = vx[0] * vy[1] - vx[1] * vy[0]
    if abs(det) < 1e-6:
        return int(round(px)), int(round(py))
    li = (px * vy[1] - py * vy[0]) / det
    lj = (vx[0] * py - vx[1] * px) / det
    return int(round(li)), int(round(lj))


def lattice_to_world(
    i: int,
    j: int,
    origin: Vec2,
    axis_x: Vec2,
    axis_y: Vec2,
) -> TileCoord:
    wc, wr = lattice_point(origin, axis_x, axis_y, i, j)
    c = max(0, min(COLS - 1, int(round(wc))))
    r = max(0, min(ROWS - 1, int(round(wr))))
    return c, r


def lattice_point(origin: Vec2, axis_x: Vec2, axis_y: Vec2, i: int, j: int) -> Vec2:
    ox, oy = origin
    return (ox + i * axis_x[0] + j * axis_y[0], oy + i * axis_x[1] + j * axis_y[1])


def lattice_cell_corners(
    i: int,
    j: int,
    origin: Vec2,
    axis_x: Vec2,
    axis_y: Vec2,
) -> ProberCorners:
    """Skew parallelogram for one lattice cell — this is the walk hitbox shape."""
    return [
        lattice_point(origin, axis_x, axis_y, i, j),
        lattice_point(origin, axis_x, axis_y, i + 1, j),
        lattice_point(origin, axis_x, axis_y, i + 1, j + 1),
        lattice_point(origin, axis_x, axis_y, i, j + 1),
    ]


def point_in_lattice_cell(
    px: float,
    py: float,
    i: int,
    j: int,
    origin: Vec2,
    axis_x: Vec2,
    axis_y: Vec2,
) -> bool:
    return _point_in_convex_quad(px, py, lattice_cell_corners(i, j, origin, axis_x, axis_y))


def lattice_cell_at_world(
    gc: float,
    gr: float,
    origin: Vec2,
    axis_x: Vec2,
    axis_y: Vec2,
) -> LatticeCoord:
    """Lattice cell whose parallelogram contains (gc, gr), else nearest cell."""
    i0, j0 = snap_to_lattice(gc, gr, origin, axis_x, axis_y)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            i, j = i0 + di, j0 + dj
            if point_in_lattice_cell(gc, gr, i, j, origin, axis_x, axis_y):
                return i, j
    return i0, j0


@dataclass
class ZoneDef:
    dx: float
    dy: float
    radius: float
    step: str


@dataclass
class DevLayout:
    play_bounds_corners: ProberCorners = field(default_factory=default_play_bounds_corners)
    storage_corners: ProberCorners = field(default_factory=default_storage_corners)
    receiving_booths: List[TileCoord] = field(default_factory=default_receiving_booths)

    spade_c0: int = 22
    spade_r1: int = 8

    prober_cx: float = 13.0
    prober_cy: float = 10.0
    # Fixed camera/background anchor — does not move when prober is dragged.
    view_anchor_c: float = 13.0
    view_anchor_r: float = 10.0
    # Depth-sort arrow: origin + tip offset (independent of prober art anchor).
    prober_front_origin_c: float = 13.0
    prober_front_origin_r: float = 10.0
    prober_front_dx: float = 2.5
    prober_front_dy: float = 2.5
    prober_sort_near_radius: float = 7.0
    prober_sort_side_clear: float = 0.35
    # Skew tile lattice: origin + two step vectors (drag arrows in editor).
    tile_origin_c: float = 13.0
    tile_origin_r: float = 10.0
    tile_axis_x: Vec2 = field(default_factory=lambda: default_tile_axes()[0])
    tile_axis_y: Vec2 = field(default_factory=lambda: default_tile_axes()[1])
    # Blocked skew-lattice cells (i, j) — paint mode stores these, not axis-aligned grid indices.
    blocked_lattice: List[LatticeCoord] = field(default_factory=list)
    # True once saved/edited — prevents reload from re-seeding an empty lattice from prober_corners.
    lattice_user_defined: bool = False
    blocked_tiles: List[TileCoord] = field(default_factory=list)
    prober_corners: ProberCorners = field(default_factory=default_prober_corners)

    finished_c: int = 22
    finished_r: int = 10

    # Draggable UI label anchors (world grid); None = auto from station geometry.
    label_storage_c: Optional[float] = None
    label_storage_r: Optional[float] = None
    label_rack_l_c: Optional[float] = None
    label_rack_l_r: Optional[float] = None
    label_rack_r_c: Optional[float] = None
    label_rack_r_r: Optional[float] = None
    label_prober_c: Optional[float] = None
    label_prober_r: Optional[float] = None
    label_mhu_c: Optional[float] = None
    label_mhu_r: Optional[float] = None
    label_chuck_l_c: Optional[float] = None
    label_chuck_l_r: Optional[float] = None
    label_chuck_r_c: Optional[float] = None
    label_chuck_r_r: Optional[float] = None

    zones: Dict[str, ZoneDef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.zones:
            self.zones = _default_zones()
        self.tile_axis_x = (float(self.tile_axis_x[0]), float(self.tile_axis_x[1]))
        self.tile_axis_y = (float(self.tile_axis_y[0]), float(self.tile_axis_y[1]))
        if not self.blocked_lattice and not self.lattice_user_defined:
            if self.blocked_tiles:
                self._migrate_world_tiles_to_lattice()
            elif not self.blocked_tiles:
                self.blocked_tiles = tiles_from_quad(self.prober_corners)
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

    def lattice_world(self, i: int, j: int) -> Vec2:
        return lattice_point(self.tile_origin(), self.tile_axis_x, self.tile_axis_y, i, j)

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
        """True when (gc, gr) lies inside a painted-open skew-lattice parallelogram."""
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

    def prober_front_origin(self) -> Vec2:
        return self.prober_front_origin_c, self.prober_front_origin_r

    def prober_front_tip(self) -> Vec2:
        return (
            self.prober_front_origin_c + self.prober_front_dx,
            self.prober_front_origin_r + self.prober_front_dy,
        )

    def prober_front_dir(self) -> Vec2:
        """Normalized direction from the sort origin toward the operator-facing side."""
        fx, fy = self.prober_front_dx, self.prober_front_dy
        ln = math.hypot(fx, fy)
        if ln < 1e-6:
            inv = 1.0 / math.sqrt(2.0)
            return inv, inv
        return fx / ln, fy / ln

    def _zone_center(self, zone_id: str) -> Vec2:
        zd = self.zones.get(zone_id)
        if zd is None:
            return self.prober_cx, self.prober_cy
        return self.prober_cx + zd.dx, self.prober_cy + zd.dy

    def storage_center(self) -> Vec2:
        cs = self.storage_corners
        return (sum(c for c, _ in cs) / len(cs), sum(r for _, r in cs) / len(cs))

    def is_inside_play_bounds(self, col: int, row: int) -> bool:
        return _point_in_convex_quad(col + 0.5, row + 0.5, self.play_bounds_corners)

    def is_storage_cell(self, col: int, row: int) -> bool:
        return _point_in_convex_quad(col + 0.5, row + 0.5, self.storage_corners)

    def label_storage(self) -> Vec2:
        if self.label_storage_c is not None and self.label_storage_r is not None:
            return self.label_storage_c, self.label_storage_r
        return self.storage_center()

    def label_rack_l(self) -> Vec2:
        if self.label_rack_l_c is not None and self.label_rack_l_r is not None:
            return self.label_rack_l_c, self.label_rack_l_r
        c, r = self._zone_center("rack_l")
        return c, r

    def label_rack_r(self) -> Vec2:
        if self.label_rack_r_c is not None and self.label_rack_r_r is not None:
            return self.label_rack_r_c, self.label_rack_r_r
        c, r = self._zone_center("rack_r")
        return c, r

    def label_prober(self) -> Vec2:
        if self.label_prober_c is not None and self.label_prober_r is not None:
            return self.label_prober_c, self.label_prober_r
        return self.prober_cx, self.prober_cy

    def label_mhu(self) -> Vec2:
        if self.label_mhu_c is not None and self.label_mhu_r is not None:
            return self.label_mhu_c, self.label_mhu_r
        return self._zone_center("mhu")

    def label_chuck_l(self) -> Vec2:
        if self.label_chuck_l_c is not None and self.label_chuck_l_r is not None:
            return self.label_chuck_l_c, self.label_chuck_l_r
        return self._zone_center("chuck_l")

    def label_chuck_r(self) -> Vec2:
        if self.label_chuck_r_c is not None and self.label_chuck_r_r is not None:
            return self.label_chuck_r_c, self.label_chuck_r_r
        return self._zone_center("chuck_r")


def _default_zones() -> Dict[str, ZoneDef]:
    return {
        "mhu": ZoneDef(0.0, 0.0, 2.0, "PROBER_WAIT"),
        "rack_l": ZoneDef(-1.75, -0.95, 1.25, "TEST_BENCH"),
        "rack_r": ZoneDef(1.75, -0.95, 1.25, "TEST_BENCH"),
        "chuck_l": ZoneDef(-2.05, 0.05, 1.3, "TEST_CHAMBER"),
        "chuck_r": ZoneDef(2.05, 0.05, 1.3, "TEST_CHAMBER"),
        "load_l": ZoneDef(-2.05, 0.75, 1.25, "PROBER_LOAD"),
        "load_r": ZoneDef(2.05, 0.75, 1.25, "PROBER_LOAD"),
    }


_layout: DevLayout | None = None

# Blueprint center — editor snaps prober + station zones here for tuning (floor unchanged).
EDITOR_STATION_CENTER: Vec2 = (13.0, 10.0)


def center_prober_stations_for_editor(lay: DevLayout) -> None:
    """Move prober and MHU/rack/chuck/load zones to blueprint center (one-shot helper)."""
    cx, cy = EDITOR_STATION_CENTER
    lay.prober_cx = cx
    lay.prober_cy = cy
    lay.prober_front_origin_c = cx
    lay.prober_front_origin_r = cy
    lay.prober_front_dx = 2.5
    lay.prober_front_dy = 2.5
    lay.zones = {k: ZoneDef(z.dx, z.dy, z.radius, z.step) for k, z in _default_zones().items()}


def recenter_play_and_storage_bounds(lay: DevLayout) -> None:
    """Reset purple play bounds (and storage data) centered on the camera anchor."""
    center = lay.view_anchor()
    lay.play_bounds_corners = axis_parallelogram_corners(
        center, 8.0, 5.0, axis_x=lay.tile_axis_x, axis_y=lay.tile_axis_y
    )
    lay.storage_corners = axis_parallelogram_corners(
        center, 4.0, 4.0, axis_x=lay.tile_axis_x, axis_y=lay.tile_axis_y
    )


def recenter_finished_checkpoint(lay: DevLayout) -> None:
    """Move finished rack checkpoint back to the default visible spot for editing."""
    lay.finished_c = 22
    lay.finished_r = 10


def center_all_editable_components(lay: DevLayout) -> None:
    """One-shot: prober, zones, tile origin, and label anchors — floor paint unchanged."""
    center_prober_stations_for_editor(lay)
    cx, cy = EDITOR_STATION_CENTER
    lay.tile_origin_c = cx
    lay.tile_origin_r = cy
    lay.view_anchor_c = cx
    lay.view_anchor_r = cy
    for name in (
        "label_storage_c",
        "label_storage_r",
        "label_rack_l_c",
        "label_rack_l_r",
        "label_rack_r_c",
        "label_rack_r_r",
        "label_prober_c",
        "label_prober_r",
        "label_mhu_c",
        "label_mhu_r",
        "label_chuck_l_c",
        "label_chuck_l_r",
        "label_chuck_r_c",
        "label_chuck_r_r",
    ):
        setattr(lay, name, None)


def _nudge_layout_stations(lay: DevLayout, dc: float, dr: float, *, nudge_zone_offsets: bool) -> None:
    lay.tile_origin_c += dc
    lay.tile_origin_r += dr

    lay.play_bounds_corners = nudge_corners(lay.play_bounds_corners, dc, dr)
    lay.storage_corners = nudge_corners(lay.storage_corners, dc, dr)
    lay.finished_c = max(0, min(COLS - 1, int(round(lay.finished_c + dc))))
    lay.finished_r = max(0, min(ROWS - 1, int(round(lay.finished_r + dr))))
    lay.spade_c0 = max(0, min(COLS - 1, int(round(lay.spade_c0 + dc))))
    lay.spade_r1 = max(0, min(ROWS - 1, int(round(lay.spade_r1 + dr))))

    lay.receiving_booths = [
        (
            max(0, min(COLS - 1, int(round(c + dc)))),
            max(0, min(ROWS - 1, int(round(r + dr)))),
        )
        for c, r in lay.receiving_booths
    ]

    for name in (
        "label_storage_c",
        "label_storage_r",
        "label_rack_l_c",
        "label_rack_l_r",
        "label_rack_r_c",
        "label_rack_r_r",
        "label_prober_c",
        "label_prober_r",
        "label_mhu_c",
        "label_mhu_r",
        "label_chuck_l_c",
        "label_chuck_l_r",
        "label_chuck_r_c",
        "label_chuck_r_r",
    ):
        v = getattr(lay, name)
        if v is not None:
            setattr(lay, name, v + (dc if name.endswith("_c") else dr))

    if nudge_zone_offsets:
        lay.zones = {
            k: ZoneDef(z.dx + dc, z.dy + dr, z.radius, z.step) for k, z in lay.zones.items()
        }


def nudge_layout_all(lay: DevLayout, dc: float, dr: float) -> None:
    """Shift the entire lab together (prober, floor, zones, labels) — background moves with prober."""
    lay.prober_cx += dc
    lay.prober_cy += dr
    lay.prober_front_origin_c += dc
    lay.prober_front_origin_r += dr
    _nudge_layout_stations(lay, dc, dr, nudge_zone_offsets=False)


def apply_prober_anchor_drag(lay: DevLayout, start: DevLayout, dc: float, dr: float) -> None:
    """Drag prober anchor — move floor/stations with it; zone offsets stay (zones follow prober)."""
    lay.prober_cx = start.prober_cx + dc
    lay.prober_cy = start.prober_cy + dr
    lay.prober_front_origin_c = start.prober_front_origin_c + dc
    lay.prober_front_origin_r = start.prober_front_origin_r + dr
    lay.tile_origin_c = start.tile_origin_c + dc
    lay.tile_origin_r = start.tile_origin_r + dr

    lay.play_bounds_corners = nudge_corners(start.play_bounds_corners, dc, dr)
    lay.storage_corners = nudge_corners(start.storage_corners, dc, dr)
    lay.finished_c = max(0, min(COLS - 1, int(round(start.finished_c + dc))))
    lay.finished_r = max(0, min(ROWS - 1, int(round(start.finished_r + dr))))
    lay.spade_c0 = max(0, min(COLS - 1, int(round(start.spade_c0 + dc))))
    lay.spade_r1 = max(0, min(ROWS - 1, int(round(start.spade_r1 + dr))))

    lay.receiving_booths = [
        (
            max(0, min(COLS - 1, int(round(c + dc)))),
            max(0, min(ROWS - 1, int(round(r + dr)))),
        )
        for c, r in start.receiving_booths
    ]

    for name in (
        "label_storage_c",
        "label_storage_r",
        "label_rack_l_c",
        "label_rack_l_r",
        "label_rack_r_c",
        "label_rack_r_r",
        "label_prober_c",
        "label_prober_r",
        "label_mhu_c",
        "label_mhu_r",
        "label_chuck_l_c",
        "label_chuck_l_r",
        "label_chuck_r_c",
        "label_chuck_r_r",
    ):
        v = getattr(start, name)
        if v is not None:
            setattr(lay, name, v + (dc if name.endswith("_c") else dr))


def default_layout() -> DevLayout:
    return DevLayout()


def load_layout() -> DevLayout:
    if not LAYOUT_PATH.exists():
        return default_layout()
    data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    if "view_anchor_c" not in data:
        data["view_anchor_c"] = float(data.get("tile_origin_c", data.get("prober_cx", 13.0)))
        data["view_anchor_r"] = float(data.get("tile_origin_r", data.get("prober_cy", 10.0)))
    zones = {k: ZoneDef(**v) for k, v in data.pop("zones", {}).items()}
    corners_raw = data.pop("prober_corners", None)
    if corners_raw is not None:
        corners: ProberCorners = [tuple(p) for p in corners_raw]  # type: ignore[misc]
    else:
        corners = prober_corners_from_legacy(
            float(data.get("prober_cx", 13.0)),
            float(data.get("prober_cy", 10.0)),
            float(data.pop("prober_half_u", 4.6)),
            float(data.pop("prober_half_v", 2.1)),
        )
    data.pop("prober_half_u", None)
    data.pop("prober_half_v", None)

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
    else:
        blocked = tiles_from_quad(corners)

    if "prober_front_origin_c" not in data:
        data["prober_front_origin_c"] = float(data.get("prober_cx", 13.0))
        data["prober_front_origin_r"] = float(data.get("prober_cy", 10.0))

    booths_raw = data.pop("receiving_booths", None)
    receiving_booths = default_receiving_booths()
    if booths_raw is not None:
        receiving_booths = [(int(c), int(r)) for c, r in booths_raw]

    play_raw = data.pop("play_bounds_corners", None)
    storage_raw = data.pop("storage_corners", None)
    if play_raw is None:
        wl = float(data.pop("wall_left", 0))
        wr = float(data.pop("wall_right", COLS))
        wt = float(data.pop("wall_top", 2))
        wb = float(data.pop("wall_bottom", ROWS))
        play_bounds_corners = rect_to_corners(wl, wt, wr, wb)
    else:
        data.pop("wall_left", None)
        data.pop("wall_right", None)
        data.pop("wall_top", None)
        data.pop("wall_bottom", None)
        play_bounds_corners = [(float(c), float(r)) for c, r in play_raw]

    if storage_raw is None:
        sc1 = float(data.pop("storage_c1", 9))
        sr1 = float(data.pop("storage_r1", 8))
        storage_corners = [(0.0, 0.0), (sc1, 0.0), (sc1, sr1), (0.0, sr1)]
    else:
        data.pop("storage_c1", None)
        data.pop("storage_r1", None)
        storage_corners = [(float(c), float(r)) for c, r in storage_raw]

    return DevLayout(
        receiving_booths=receiving_booths,
        blocked_lattice=lattice,
        lattice_user_defined=lattice_user_defined,
        blocked_tiles=blocked,
        prober_corners=corners,
        zones=zones,
        play_bounds_corners=play_bounds_corners,
        storage_corners=storage_corners,
        **data,
    )


def _write_layout_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def _replace_with_retry(src: Path, dst: Path, *, attempts: int = 6) -> bool:
    import time

    for i in range(attempts):
        if i:
            time.sleep(0.04 * i)
        try:
            os.replace(src, dst)
            return True
        except PermissionError:
            continue
        except OSError as e:
            if getattr(e, "winerror", None) == 5:
                continue
            raise
    return False


def save_layout(layout: DevLayout) -> bool:
    """Persist layout; returns False if the file is locked (e.g. open in the IDE)."""
    payload: Dict[str, Any] = asdict(layout)
    payload["zones"] = {k: asdict(v) for k, v in layout.zones.items()}
    payload["blocked_lattice"] = [[i, j] for i, j in layout.blocked_lattice]
    payload["lattice_user_defined"] = layout.lattice_user_defined
    payload["receiving_booths"] = [[c, r] for c, r in layout.receiving_booths]
    payload["play_bounds_corners"] = [list(p) for p in layout.play_bounds_corners]
    payload["storage_corners"] = [list(p) for p in layout.storage_corners]
    payload.pop("blocked_tiles", None)
    payload["tile_axis_x"] = list(layout.tile_axis_x)
    payload["tile_axis_y"] = list(layout.tile_axis_y)
    payload.pop("prober_corners", None)
    text = json.dumps(payload, indent=2)
    tmp = LAYOUT_PATH.with_suffix(".json.tmp")
    try:
        _write_layout_text(tmp, text)
    except OSError:
        return False

    if _replace_with_retry(tmp, LAYOUT_PATH):
        return True

    try:
        _write_layout_text(LAYOUT_PATH, text)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return True
    except OSError:
        pass

    # Keep .tmp so edits are not lost; caller still has in-memory layout.
    return False


def get_layout() -> DevLayout:
    global _layout
    if _layout is None:
        _layout = load_layout() if LAYOUT_PATH.exists() else default_layout()
    return _layout


def reload_layout() -> DevLayout:
    global _layout
    _layout = load_layout()
    return _layout


def apply_layout(layout: DevLayout) -> None:
    global _layout
    _layout = layout


def commit_layout(layout: DevLayout) -> bool:
    """Apply in-memory layout and write dev_layout.json (editor changes persist)."""
    if layout.blocked_lattice:
        layout.lattice_user_defined = True
    apply_layout(layout)
    return save_layout(layout)


def flush_layout_to_disk() -> None:
    """Best-effort save on exit (shift end, window close, process exit)."""
    lay = _layout
    if lay is not None:
        try:
            save_layout(lay)
        except OSError:
            pass


atexit.register(flush_layout_to_disk)
