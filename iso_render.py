"""Isometric floor, lab art overlays, operator sprites, world UI."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, List, Optional, Sequence, Tuple

import pygame

if TYPE_CHECKING:
    from game_assets import GameAssets

from game_assets import OPERATOR_HEIGHT_FACTOR, PROBER_WIDTH_FACTOR

from constants import (
    COLS,
    FLOOR,
    INVENTORY_WAIT_S,
    PLAN_LINE,
    ROWS,
    SCREEN_H,
    SCREEN_W,
)
from lab import walkable
from lab import (
    TEST_CYCLE,
    Cell,
    ChuckStatus,
    StationZone,
    TestSpec,
    WaferOrder,
    all_station_tiles,
    chuck_status_for_side,
    config_rack_zones,
    mhu_zone,
    prober_chuck_zones,
    prober_station_zones,
    player_draws_in_front_of_prober,
    prober_visual_center,
    test_label,
)

Point = Tuple[float, float]


@dataclass
class IsoView:
    hw: float
    hh: float
    ox: float
    oy: float
    wall_h: float = 40.0

    def center(self, col: float, row: float) -> Point:
        return (col - row) * self.hw + self.ox, (col + row) * self.hh + self.oy

    def corners_at(self, col: float, row: float) -> List[Point]:
        cx, cy = self.center(col, row)
        return [
            (cx - self.hw, cy),
            (cx, cy - self.hh),
            (cx + self.hw, cy),
            (cx, cy + self.hh),
        ]

    def corners_floor(self, col: int, row: int) -> List[Point]:
        cx, cy = self.center(float(col), float(row))
        return [
            (cx - self.hw, cy),
            (cx, cy - self.hh),
            (cx + self.hw, cy),
            (cx, cy + self.hh),
        ]

    def corners_top(self, col: int, row: int) -> List[Point]:
        cx, cy = self.center(float(col), float(row))
        dy = -self.wall_h
        return [
            (cx - self.hw, cy + dy),
            (cx, cy - self.hh + dy),
            (cx + self.hw, cy + dy),
            (cx, cy + self.hh + dy),
        ]


def _iso_view_in_rect(
    bounds: pygame.Rect,
    hw: float,
    hh: float,
    *,
    wall_h: float = 40.0,
    vertical_bias: float = 0.52,
) -> IsoView:
    """Place the COLS×ROWS diamond grid inside a screen/world rectangle."""
    minx = miny = 1e9
    maxx = maxy = -1e9
    for r in range(ROWS):
        for c in range(COLS):
            x, y = (c - r) * hw, (c + r) * hh
            minx = min(minx, x - hw, x + hw)
            maxx = max(maxx, x - hw, x + hw)
            miny = min(miny, y - hh, y + hh)
            maxy = max(maxy, y - hh, y + hh + wall_h)
    w = maxx - minx
    h = maxy - miny
    pad_x = bounds.x + (bounds.width - w) * 0.5 - minx
    pad_y = bounds.y + (bounds.height - h) * vertical_bias - miny
    return IsoView(hw, hh, pad_x, pad_y, wall_h)


def make_iso_view(screen_w: int = SCREEN_W, screen_h: int = SCREEN_H) -> IsoView:
    hw, hh = 36.0, 21.0
    wall_h = 40.0
    return _iso_view_in_rect(
        pygame.Rect(0, 0, screen_w, screen_h),
        hw,
        hh,
        wall_h=wall_h,
        vertical_bias=0.52,
    )


def _shade(rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )


def cell_base_color(cell: Cell) -> Tuple[int, int, int]:
    from constants import WALL

    if cell == Cell.WALL:
        return WALL
    return FLOOR


def draw_wall_block(
    surf: pygame.Surface,
    view: IsoView,
    col: int,
    row: int,
    base: Tuple[int, int, int],
) -> None:
    b = view.corners_floor(col, row)
    t = view.corners_top(col, row)
    left_b, top_b, right_b, bot_b = b[0], b[1], b[2], b[3]
    left_t, top_t, right_t, bot_t = t[0], t[1], t[2], t[3]

    left_face = [left_b, bot_b, bot_t, left_t]
    pygame.draw.polygon(surf, _shade(base, 0.72), left_face)
    pygame.draw.polygon(surf, _shade(base, 0.58), [right_b, bot_b, bot_t, right_t])
    pygame.draw.polygon(surf, _shade(base, 1.08), [left_t, top_t, right_t, bot_t])
    pygame.draw.lines(surf, (18, 20, 26), True, left_face, 1)
    pygame.draw.lines(surf, (18, 20, 26), True, [left_t, top_t, right_t, bot_t], 1)


def _blueprint_floor(surf: pygame.Surface, view: IsoView, col: int, row: int, highlight: bool) -> None:
    poly = view.corners_floor(col, row)
    tint = _shade(FLOOR, 1.04 if (col + row) % 2 == 0 else 0.96)
    pygame.draw.polygon(surf, tint, poly)
    dim = _shade(PLAN_LINE, 0.42)
    pygame.draw.lines(surf, dim, True, poly, 1)
    cx, cy = view.center(float(col), float(row))
    pygame.draw.line(surf, dim, (cx - view.hw * 0.35, cy), (cx + view.hw * 0.35, cy), 1)
    pygame.draw.line(surf, dim, (cx, cy - view.hh * 0.35), (cx, cy + view.hh * 0.35), 1)
    if highlight:
        pygame.draw.polygon(surf, (255, 228, 120), poly, 3)


def draw_floor_tile(
    surf: pygame.Surface,
    view: IsoView,
    col: int,
    row: int,
    cell: Cell,
    highlight: bool,
) -> None:
    if cell == Cell.WALL:
        return
    _blueprint_floor(surf, view, col, row, highlight)


def _box_prism(
    surf: pygame.Surface,
    view: IsoView,
    col: int,
    row: int,
    w_frac: float,
    d_frac: float,
    h_scale: float,
    top: Tuple[int, int, int],
    side: Tuple[int, int, int],
    front: Tuple[int, int, int],
) -> None:
    cx, cy = view.center(float(col), row + 0.08)
    hw, hh = view.hw * w_frac, view.hh * d_frac
    h = view.wall_h * h_scale
    # Floor diamond slice → extruded box (back-left origin)
    bl = (cx - hw * 0.35, cy + hh * 0.15)
    br = (cx + hw * 0.55, cy + hh * 0.35)
    fr = (cx + hw * 0.15, cy + hh * 0.85)
    fl = (cx - hw * 0.75, cy + hh * 0.65)
    base = [bl, br, fr, fl]
    top_pts = [(p[0], p[1] - h) for p in base]
    pygame.draw.polygon(surf, side, [bl, fl, (fl[0], fl[1] - h), (bl[0], bl[1] - h)])
    pygame.draw.polygon(surf, front, [fr, br, (br[0], br[1] - h), (fr[0], fr[1] - h)])
    pygame.draw.polygon(surf, top, top_pts)
    pygame.draw.lines(surf, (12, 14, 20), True, top_pts, 1)


def draw_station_3d(surf: pygame.Surface, view: IsoView, col: int, row: int, cell: Cell) -> None:
    if cell not in (
        Cell.RECEIVING,
        Cell.PROBER_LOAD,
        Cell.PROBER_WAIT,
        Cell.TEST_BENCH,
        Cell.TEST_CHAMBER,
        Cell.FINISHED_RACK,
    ):
        return
    if cell == Cell.RECEIVING:
        _box_prism(surf, view, col, row, 0.9, 0.9, 0.22, (95, 105, 120), (72, 78, 92), (82, 88, 102))
        _box_prism(surf, view, col, row - 0.12, 0.35, 0.35, 0.12, (200, 205, 215), (150, 155, 165), (170, 175, 185))
    elif cell == Cell.PROBER_LOAD:
        _box_prism(surf, view, col, row, 1.05, 0.95, 0.38, (110, 100, 135), (78, 72, 98), (92, 86, 118))
        pygame.draw.circle(surf, (60, 200, 140), (int(view.center(col + 0.1, row + 0.05)[0]), int(view.center(col + 0.1, row + 0.05)[1] - view.wall_h * 0.28)), int(view.hh * 0.35))
    elif cell == Cell.PROBER_WAIT:
        _box_prism(surf, view, col, row, 0.95, 0.9, 0.55, (105, 98, 140), (78, 74, 108), (88, 82, 120))
        cx, cy = view.center(col + 0.02, row + 0.02)
        pygame.draw.rect(
            surf,
            (40, 200, 255),
            (int(cx - view.hw * 0.25), int(cy - view.wall_h * 0.62), int(view.hw * 0.5), int(view.hh * 0.55)),
            border_radius=2,
        )
    elif cell == Cell.TEST_BENCH:
        _box_prism(surf, view, col, row, 1.1, 0.75, 0.28, (90, 130, 120), (62, 95, 88), (72, 108, 100))
        cx, cy = view.center(col, row)
        pygame.draw.rect(
            surf,
            (30, 40, 45),
            (int(cx - view.hw * 0.35), int(cy - view.wall_h * 0.38), int(view.hw * 0.7), int(view.hh * 0.5)),
            2,
        )
    elif cell == Cell.TEST_CHAMBER:
        _box_prism(surf, view, col, row, 1.0, 1.0, 0.5, (130, 88, 72), (95, 64, 52), (108, 74, 60))
        cx, cy = view.center(col, row)
        w, h = int(view.hw * 0.45), int(view.hh * 0.9)
        pygame.draw.ellipse(surf, (120, 200, 240), (int(cx - w * 0.5), int(cy - view.wall_h * 0.55), w, h))
        pygame.draw.ellipse(surf, (40, 120, 160), (int(cx - w * 0.5), int(cy - view.wall_h * 0.55), w, h), 2)
    else:  # FINISHED_RACK
        for i, dy in enumerate((0.0, -0.08, -0.16)):
            _box_prism(surf, view, col, row + dy * 0.5, 0.85 - i * 0.05, 0.85 - i * 0.05, 0.18, (95, 120, 95), (72, 92, 72), (82, 102, 82))


def draw_pending_wafer(
    surf: pygame.Surface,
    view: IsoView,
    col: int,
    row: int,
    assets: Optional["GameAssets"] = None,
) -> None:
    cx, cy = view.center(float(col), float(row))
    cy -= view.hh * 0.15
    if assets is not None and assets.wafer is not None:
        icon = assets.wafer_icon(int(view.hh * 1.1))
        surf.blit(icon, (int(cx - icon.get_width() / 2), int(cy - icon.get_height() * 0.85)))
        return
    pygame.draw.ellipse(surf, (215, 220, 230), (int(cx - view.hw * 0.28), int(cy - view.hh * 0.12), int(view.hw * 0.56), int(view.hh * 0.38)))
    pygame.draw.ellipse(surf, (120, 125, 140), (int(cx - view.hw * 0.28), int(cy - view.hh * 0.12), int(view.hw * 0.56), int(view.hh * 0.38)), 1)
    pygame.draw.circle(surf, (255, 230, 140), (int(cx), int(cy - view.hh * 0.35)), int(view.hh * 0.22))


def draw_progress_at_world(
    surf: pygame.Surface,
    view: IsoView,
    col: float,
    row: float,
    progress: float,
    bar_color: Tuple[int, int, int],
    caption: str,
    font: pygame.font.Font,
    *,
    bar_width: Optional[int] = None,
) -> None:
    """Progress bar (progress 0–1) floating above a world position."""
    from constants import WORLD_PROGRESS_BAR_W

    cx, cy = view.center(col, row)
    bw = bar_width if bar_width is not None else WORLD_PROGRESS_BAR_W
    bx = int(cx - bw * 0.5)
    by = int(cy - view.wall_h - view.hh * 2.2)
    bh = 8
    pygame.draw.rect(surf, (28, 30, 38), (bx, by, bw, bh), border_radius=3)
    fw = max(2, int(bw * min(1.0, max(0.0, progress))))
    pygame.draw.rect(surf, bar_color, (bx, by, fw, bh), border_radius=3)
    pygame.draw.rect(surf, (90, 95, 110), (bx, by, bw, bh), 1, border_radius=3)
    cap = font.render(caption, True, (210, 215, 230))
    surf.blit(cap, (bx + bw // 2 - cap.get_width() // 2, by - cap.get_height() - 2))


def draw_progress_above_tile(
    surf: pygame.Surface,
    view: IsoView,
    col: int,
    row: int,
    frac: float,
    denom: float,
    bar_color: Tuple[int, int, int],
    caption: str,
    font: pygame.font.Font,
) -> None:
    draw_progress_at_world(
        surf,
        view,
        float(col),
        float(row),
        min(1.0, max(0.0, frac) / max(0.001, denom)),
        bar_color,
        caption,
        font,
    )


def draw_chuck_status_badge(
    surf: pygame.Surface,
    view: IsoView,
    col: float,
    row: float,
    status: ChuckStatus,
    font: pygame.font.Font,
    *,
    side_label: str,
) -> None:
    productive = status == ChuckStatus.PRODUCTIVE
    fill = (28, 72, 42) if productive else (72, 58, 22)
    border = (70, 210, 100) if productive else (235, 200, 70)
    text_color = (170, 255, 190) if productive else (255, 235, 150)
    label = "PRODUCTIVE" if productive else "STANDBY"
    caption = f"{side_label} · {label}"
    cx, cy = view.center(col, row)
    cy -= view.hh * 5.6
    text = font.render(caption, True, text_color)
    pad_x, pad_y = 7, 4
    bx = int(cx - text.get_width() / 2 - pad_x)
    by = int(cy - text.get_height() / 2 - pad_y)
    bw = text.get_width() + pad_x * 2
    bh = text.get_height() + pad_y * 2
    pygame.draw.rect(surf, fill, (bx, by, bw, bh), border_radius=5)
    pygame.draw.rect(surf, border, (bx, by, bw, bh), 2, border_radius=5)
    surf.blit(text, (int(cx - text.get_width() / 2), int(cy - text.get_height() / 2)))


def draw_floating_label(
    surf: pygame.Surface,
    view: IsoView,
    col: float,
    row: float,
    text: str,
    font: pygame.font.Font,
    *,
    color: Tuple[int, int, int] = (255, 245, 200),
    lift: float = 2.8,
) -> None:
    cx, cy = view.center(col, row)
    cy -= view.hh * lift
    label = font.render(text, True, color)
    pad_x, pad_y = 6, 3
    bx = int(cx - label.get_width() / 2 - pad_x)
    by = int(cy - label.get_height() / 2 - pad_y)
    bw = label.get_width() + pad_x * 2
    bh = label.get_height() + pad_y * 2
    pygame.draw.rect(surf, (20, 24, 32), (bx, by, bw, bh), border_radius=4)
    pygame.draw.rect(surf, (100, 200, 170), (bx, by, bw, bh), 1, border_radius=4)
    surf.blit(label, (int(cx - label.get_width() / 2), int(cy - label.get_height() / 2)))


def draw_zone_hitbox(
    surf: pygame.Surface,
    view: IsoView,
    zone: StationZone,
    color: Tuple[int, int, int],
    *,
    active: bool = False,
    show_radius: bool = False,
) -> None:
    pts = [(int(p[0]), int(p[1])) for p in view.corners_at(zone.col, zone.row)]
    pygame.draw.polygon(surf, color, pts, 2)
    if active:
        pygame.draw.polygon(surf, (255, 228, 120), pts, 3)
    if show_radius:
        draw_zone_interact_radius(surf, view, zone, color)


def draw_zone_interact_radius(
    surf: pygame.Surface,
    view: IsoView,
    zone: StationZone,
    color: Tuple[int, int, int],
) -> None:
    """Debug: interaction radius in grid space mapped to screen."""
    ring: List[Tuple[int, int]] = []
    for i in range(32):
        ang = (i / 32) * math.tau
        gc = zone.col + math.cos(ang) * zone.radius
        gr = zone.row + math.sin(ang) * zone.radius
        sx, sy = view.center(gc, gr)
        ring.append((int(sx), int(sy)))
    pygame.draw.lines(surf, color, True, ring, 1)
    cx, cy = view.center(zone.col, zone.row)
    pygame.draw.circle(surf, color, (int(cx), int(cy)), 3)


def draw_walkable_debug(
    surf: pygame.Surface,
    view: IsoView,
    cells: List[List[Cell]],
    font: Optional[pygame.font.Font] = None,
) -> None:
    """Debug overlay: walkable skew-lattice cells (actual movement hitboxes)."""
    from dev_layout import get_layout
    from lab import Cell as C, receiving_booths

    tile_colors: dict[Cell, Tuple[int, int, int, int]] = {
        C.FLOOR: (70, 130, 210, 42),
        C.RECEIVING: (230, 190, 70, 75),
        C.PROBER_LOAD: (190, 195, 220, 80),
        C.PROBER_WAIT: (120, 180, 255, 85),
        C.TEST_BENCH: (90, 210, 160, 80),
        C.TEST_CHAMBER: (255, 150, 80, 80),
        C.FINISHED_RACK: (120, 200, 120, 80),
    }

    from lab import walkable

    lay = get_layout()
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for i in range(-28, 29):
        for j in range(-28, 29):
            if not lay.is_cell_walkable(i, j):
                continue
            wc, wr = lay.cell_center(i, j)
            if not walkable(cells, wc, wr):
                continue
            ic, ir = int(round(wc)), int(round(wr))
            cell = cells[ir][ic] if 0 <= ic < COLS and 0 <= ir < ROWS else C.FLOOR
            rgba = tile_colors.get(cell, (160, 160, 160, 40))
            corners = lay.lattice_corners(i, j)
            pts = [(int(view.center(c, r)[0]), int(view.center(c, r)[1])) for c, r in corners]
            if len(pts) >= 3:
                pygame.draw.polygon(layer, rgba, pts)
                pygame.draw.polygon(layer, (rgba[0], rgba[1], rgba[2], 120), pts, 1)
    surf.blit(layer, (0, 0))

    from lab import INTERACT_RADIUS

    booth_color = (230, 190, 70)
    for c, r in receiving_booths():
        _draw_tile_interact_radius(surf, view, float(c), float(r), INTERACT_RADIUS, booth_color)

    if font is not None:
        for i in range(-28, 29):
            for j in range(-28, 29):
                if not lay.is_cell_walkable(i, j):
                    continue
                wc, wr = lay.cell_center(i, j)
                if not walkable(cells, wc, wr):
                    continue
                cx, cy = view.center(wc, wr)
                tag = font.render(f"{i},{j}", True, (200, 205, 220))
                surf.blit(tag, (int(cx - tag.get_width() / 2), int(cy - 6)))


def _draw_tile_interact_radius(
    surf: pygame.Surface,
    view: IsoView,
    col: float,
    row: float,
    radius: float,
    color: Tuple[int, int, int],
) -> None:
    ring: List[Tuple[int, int]] = []
    for i in range(28):
        ang = (i / 28) * math.tau
        sx, sy = view.center(col + math.cos(ang) * radius, row + math.sin(ang) * radius)
        ring.append((int(sx), int(sy)))
    pygame.draw.lines(surf, color, True, ring, 1)


def draw_debug_legend(
    surf: pygame.Surface,
    font: pygame.font.Font,
) -> None:
    lines = [
        "DEBUG: blue=walkable floor  gold=receive  cyan=MHU",
        "green=config  orange=test  gray=load  rings=interact radius",
    ]
    y = surf.get_height() - 72
    for line in lines:
        t = font.render(line, True, (180, 190, 210))
        surf.blit(t, (12, y))
        y += 16


def _blit_operator(
    surf: pygame.Surface,
    view: IsoView,
    assets: "GameAssets",
    col: float,
    row: float,
    operator: int,
    *,
    facing_right: bool,
    moving: bool,
    carrying: bool,
) -> None:
    cx, cy = view.center(col, row)
    sprite_h = int(view.hh * OPERATOR_HEIGHT_FACTOR)
    sprite = assets.operator_frame(
        operator,
        facing_right=facing_right,
        moving=moving,
        carrying=carrying,
        sprite_h=sprite_h,
    )
    foot_y = cy + view.hh * 0.15
    surf.blit(sprite, (int(cx - sprite.get_width() / 2), int(foot_y - sprite.get_height())))


def draw_players_iso(
    surf: pygame.Surface,
    view: IsoView,
    players: Sequence[Tuple[float, float, Tuple[int, int, int]]],
    carries: Optional[Sequence[bool]] = None,
    *,
    assets: Optional["GameAssets"] = None,
    moving: Optional[Sequence[bool]] = None,
    facings: Optional[Sequence[bool]] = None,
    operators: Optional[Sequence[int]] = None,
) -> None:
    if assets is not None:
        ordered = sorted(enumerate(players), key=lambda t: t[1][0] + t[1][1])
        for i, (col, row, _rgb) in ordered:
            carry = carries is not None and i < len(carries) and carries[i]
            mv = moving is not None and i < len(moving) and moving[i]
            face = facings[i] if facings is not None and i < len(facings) else True
            op = operators[i] if operators is not None and i < len(operators) else 0
            _blit_operator(
                surf,
                view,
                assets,
                col,
                row,
                op,
                facing_right=face,
                moving=mv,
                carrying=carry,
            )
        return

    ordered = sorted(enumerate(players), key=lambda t: t[1][0] + t[1][1])
    for i, (col, row, rgb) in ordered:
        cx, cy = view.center(col, row)
        body_w = view.hw * 0.55
        body_h = view.hh * 2.1
        top = cy - body_h * 0.55 - view.wall_h * 0.15
        pygame.draw.ellipse(
            surf,
            rgb,
            (int(cx - body_w), int(top), int(2 * body_w), int(body_h * 1.1)),
        )
        pygame.draw.ellipse(
            surf,
            _shade(rgb, 0.55),
            (int(cx - body_w), int(top), int(2 * body_w), int(body_h * 1.1)),
            2,
        )
        head_r = view.hh * 0.75
        pygame.draw.circle(
            surf,
            _shade(rgb, 1.05),
            (int(cx), int(top - head_r * 0.35)),
            int(head_r),
        )
        pygame.draw.circle(
            surf,
            _shade(rgb, 0.5),
            (int(cx), int(top - head_r * 0.35)),
            int(head_r),
            2,
        )
        if carries is not None and i < len(carries) and carries[i]:
            pygame.draw.ellipse(
                surf,
                (210, 215, 225),
                (int(cx - view.hw * 0.25), int(top + body_h * 0.35), int(view.hw * 0.5), int(view.hh * 0.45)),
            )
            pygame.draw.ellipse(surf, (90, 95, 110), (int(cx - view.hw * 0.25), int(top + body_h * 0.35), int(view.hw * 0.5), int(view.hh * 0.45)), 1)


def draw_objective_arrow(
    surf: pygame.Surface,
    view: IsoView,
    from_col: float,
    from_row: float,
    to_col: float,
    to_row: float,
    *,
    pulse_t: float,
) -> None:
    """Arrow from the player toward the active objective tile."""
    fx, fy = view.center(from_col, from_row)
    fy -= view.hh * 0.35
    tx, ty = view.center(float(to_col), float(to_row))
    ty -= view.hh * 0.45

    dx, dy = tx - fx, ty - fy
    dist = math.hypot(dx, dy)
    if dist < 28:
        return

    ux, uy = dx / dist, dy / dist
    along = min(dist * 0.55, dist - 36)
    ax, ay = fx + ux * along, fy + uy * along

    pulse = 0.5 + 0.5 * math.sin(pulse_t * 4.5)
    size = 11 + pulse * 5
    px, py = -uy, ux
    tip = (ax + ux * size * 1.2, ay + uy * size * 1.2)
    back = (ax - ux * size * 0.55, ay - uy * size * 0.55)
    left = (back[0] + px * size * 0.55, back[1] + py * size * 0.55)
    right = (back[0] - px * size * 0.55, back[1] - py * size * 0.55)
    pts = [tip, left, right]

    glow = pygame.Surface((int(size * 4), int(size * 4)), pygame.SRCALPHA)
    pygame.draw.polygon(glow, (255, 210, 60, 70), [(p[0] - ax + size * 2, p[1] - ay + size * 2) for p in pts])
    surf.blit(glow, (int(ax - size * 2), int(ay - size * 2)))
    pygame.draw.polygon(surf, (255, 232, 110), pts)
    pygame.draw.polygon(surf, (230, 150, 40), pts, 2)

    # Short guide line toward the goal
    lx, ly = fx + ux * 18, fy + uy * 18
    pygame.draw.line(surf, (255, 220, 100), (int(lx), int(ly)), (int(ax), int(ay)), 3)


def _draw_station_markers_art(
    surf: pygame.Surface,
    view: IsoView,
    cells: List[List[Cell]],
    hl_set: set[Tuple[int, int]],
    assets: "GameAssets",
    *,
    debug_font: Optional[pygame.font.Font] = None,
) -> None:
    from lab import Cell as C

    zone_colors = {
        Cell.PROBER_WAIT: (120, 180, 255),
        Cell.TEST_BENCH: (100, 200, 170),
        Cell.TEST_CHAMBER: (255, 160, 90),
        Cell.PROBER_LOAD: (180, 190, 210),
    }
    show_debug = debug_font is not None
    for z in prober_station_zones():
        draw_zone_hitbox(surf, view, z, zone_colors[z.step], active=False, show_radius=show_debug)
        if show_debug and debug_font is not None:
            cx, cy = view.center(z.col, z.row)
            tag = debug_font.render(z.zone_id, True, zone_colors[z.step])
            surf.blit(tag, (int(cx - tag.get_width() / 2), int(cy - view.hh * 3.2)))

    if show_debug:
        for c, r in all_station_tiles(cells, C.FINISHED_RACK):
            from lab import INTERACT_RADIUS

            _draw_tile_interact_radius(surf, view, float(c), float(r), INTERACT_RADIUS, (140, 200, 140))


def _prober_sprite_sort_line(
    assets: "GameAssets",
    center: Point,
    cluster_w: float,
) -> float:
    """Screen Y of the prober's floor contact line (larger Y = closer to camera)."""
    cx, cy = center
    if assets.stations is None:
        return cy
    sw, sh = assets.stations.get_size()
    tw = int(cluster_w)
    th = max(1, int(sh * tw / sw))
    return cy + int(th * 0.08)


def draw_prober_and_players_depth_sorted(
    surf: pygame.Surface,
    view: IsoView,
    assets: "GameAssets",
    players: Sequence[Tuple[float, float, Tuple[int, int, int]]],
    carries: Optional[Sequence[bool]] = None,
    *,
    moving: Optional[Sequence[bool]] = None,
    facings: Optional[Sequence[bool]] = None,
    operators: Optional[Sequence[int]] = None,
) -> None:
    """Draw operator vs prober — only depth-fight when the player is near the machine."""
    pc, pr = prober_visual_center()
    prober_center = view.center(pc, pr)
    cluster_w = view.hw * PROBER_WIDTH_FACTOR

    def _draw_prober() -> None:
        assets.draw_prober_cluster(surf, prober_center, cluster_w)

    def _draw_players() -> None:
        draw_players_iso(
            surf,
            view,
            players,
            carries,
            assets=assets,
            moving=moving,
            facings=facings,
            operators=operators,
        )

    if not players:
        _draw_prober()
        return

    pcol, prow = players[0][0], players[0][1]
    _, player_foot_y = view.center(pcol, prow)
    player_foot_y += view.hh * 0.15
    prober_foot_y = _prober_sprite_sort_line(assets, prober_center, cluster_w)
    player_in_front = player_draws_in_front_of_prober(
        pcol,
        prow,
        player_foot_y=player_foot_y,
        prober_foot_y=prober_foot_y,
    )

    if player_in_front:
        _draw_prober()
        _draw_players()
    else:
        _draw_players()
        _draw_prober()


def draw_storage_queue_label(
    surf: pygame.Surface,
    view: IsoView,
    queue_count: int,
    font: pygame.font.Font,
) -> None:
    from dev_layout import get_layout

    cx, cy = get_layout().label_storage()
    label = f"{queue_count} in queue" if queue_count != 1 else "1 in queue"
    draw_floating_label(
        surf,
        view,
        cx,
        cy,
        label,
        font,
        color=(255, 235, 170),
        lift=3.2,
    )


def _draw_world_ui_overlays(
    surf: pygame.Surface,
    view: IsoView,
    font: pygame.font.Font,
    *,
    orders: List[WaferOrder],
    dial_by_side: dict[str, int],
    bench_rack_side: Optional[str],
    mhu_order: Optional[WaferOrder],
    inv_prog: float,
    queue_count: int,
) -> None:
    from dev_layout import get_layout
    from lab import TEST_CYCLE, chamber_order_on_side, test_label

    lay = get_layout()

    for side, chuck_pos in (("l", lay.label_chuck_l()), ("r", lay.label_chuck_r())):
        cc, cr = chuck_pos
        draw_chuck_status_badge(
            surf,
            view,
            cc,
            cr,
            chuck_status_for_side(orders, side),
            font,
            side_label="L" if side == "l" else "R",
        )

    if mhu_order is not None and inv_prog > 0:
        mc, mr = lay.label_mhu()
        draw_progress_at_world(
            surf,
            view,
            mc,
            mr,
            min(1.0, max(0.0, inv_prog / INVENTORY_WAIT_S)),
            (110, 185, 255),
            "MHU inventory",
            font,
        )

    for side, rack_pos, chuck_pos in (
        ("l", lay.label_rack_l(), lay.label_chuck_l()),
        ("r", lay.label_rack_r(), lay.label_chuck_r()),
    ):
        ch = chamber_order_on_side(orders, side)
        if ch:
            cc, cr = chuck_pos
            draw_progress_at_world(
                surf,
                view,
                cc,
                cr,
                ch.chamber_progress(),
                (255, 150, 90),
                f"{'L' if side == 'l' else 'R'} chuck test",
                font,
            )
            rc, rr = rack_pos
            draw_floating_label(
                surf,
                view,
                rc,
                rr,
                f"Test: {test_label(ch.required)}",
                font,
                color=(255, 245, 200),
                lift=4.5,
            )
            continue

        bench_o = None
        for o in orders:
            if o.prober_side == side and o.next_expected() == Cell.TEST_BENCH:
                bench_o = o
                break
        if bench_o is None:
            continue
        rc, rr = rack_pos
        if bench_rack_side == side:
            dial = TEST_CYCLE[dial_by_side.get(side, 0) % len(TEST_CYCLE)]
            draw_floating_label(
                surf,
                view,
                rc,
                rr,
                f"Dial: {test_label(dial)}",
                font,
                color=(160, 230, 200),
                lift=4.5,
            )
        else:
            draw_floating_label(
                surf,
                view,
                rc,
                rr,
                f"Test: {test_label(bench_o.required)}",
                font,
                color=(255, 245, 200),
                lift=4.5,
            )

    if queue_count > 0:
        draw_storage_queue_label(surf, view, queue_count, font)


def draw_world_iso(
    surf: pygame.Surface,
    view: IsoView,
    cells: List[List[Cell]],
    highlights: Iterable[Tuple[int, int]],
    *,
    pending_wafer_tiles: Optional[List[Tuple[int, int]]] = None,
    world_progress_font: Optional[pygame.font.Font] = None,
    assets: Optional["GameAssets"] = None,
    objective_arrow: Optional[Tuple[float, float, int, int, float]] = None,
    floor_debug: bool = False,
    orders: Optional[List[WaferOrder]] = None,
    dial_by_side: Optional[dict[str, int]] = None,
    bench_rack_side: Optional[str] = None,
    mhu_order: Optional[WaferOrder] = None,
    inv_prog: float = 0.0,
    queue_count: int = 0,
    ui_preview: bool = False,
) -> None:
    order_list: List[WaferOrder] = list(orders or [])
    dials = dial_by_side if dial_by_side is not None else {"l": 0, "r": 0}
    if ui_preview:
        inv_prog = INVENTORY_WAIT_S * 0.65
        queue_count = max(queue_count, 3)
        dials = {"l": 1, "r": 2}
    hl_set = set(highlights)
    pending = set(pending_wafer_tiles or [])
    show_floor = floor_debug

    if assets is not None:
        assets.draw_background(surf)
        if show_floor:
            draw_walkable_debug(surf, view, cells, world_progress_font)
        _draw_station_markers_art(
            surf,
            view,
            cells,
            hl_set,
            assets,
            debug_font=world_progress_font if show_floor else None,
        )
        if show_floor and world_progress_font is not None:
            draw_debug_legend(surf, world_progress_font)
        for c, r in pending:
            draw_pending_wafer(surf, view, c, r, assets)
        if objective_arrow is not None:
            pcol, prow, tcol, trow, pulse_t = objective_arrow
            draw_objective_arrow(surf, view, pcol, prow, tcol, trow, pulse_t=pulse_t)
        if world_progress_font is not None:
            _draw_world_ui_overlays(
                surf,
                view,
                world_progress_font,
                orders=order_list,
                dial_by_side=dials,
                bench_rack_side=bench_rack_side,
                mhu_order=mhu_order,
                inv_prog=inv_prog,
                queue_count=queue_count,
            )
        return

    for depth in range(COLS + ROWS - 1):
        for c in range(COLS):
            r = depth - c
            if not (0 <= r < ROWS):
                continue
            cell = cells[r][c]
            if cell == Cell.WALL:
                draw_wall_block(surf, view, c, r, cell_base_color(cell))
            else:
                draw_floor_tile(surf, view, c, r, cell, False)

    for depth in range(COLS + ROWS - 1):
        for c in range(COLS):
            r = depth - c
            if not (0 <= r < ROWS):
                continue
            cell = cells[r][c]
            if cell != Cell.WALL and cell != Cell.FLOOR:
                draw_station_3d(surf, view, c, r, cell)

    for depth in range(COLS + ROWS - 1):
        for c in range(COLS):
            r = depth - c
            if not (0 <= r < ROWS):
                continue
            if (c, r) in pending:
                draw_pending_wafer(surf, view, c, r, assets)

    if world_progress_font is not None:
        _draw_world_ui_overlays(
            surf,
            view,
            world_progress_font,
            orders=order_list,
            dial_by_side=dials,
            bench_rack_side=bench_rack_side,
            mhu_order=mhu_order,
            inv_prog=inv_prog,
            queue_count=queue_count,
        )
