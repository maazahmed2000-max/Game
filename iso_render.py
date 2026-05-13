"""Isometric floor (blueprint-style), extruded walls, 3D-style station props, world UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import pygame

from constants import (
    CHAMBER_RUN_S,
    COLS,
    FLOOR,
    INVENTORY_WAIT_S,
    PLAN_LINE,
    ROWS,
    SCREEN_H,
    SCREEN_W,
)
from lab import Cell, all_station_tiles

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


def make_iso_view() -> IsoView:
    hw, hh = 36.0, 21.0
    wall_h = 40.0
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
    hud = 110
    pad_x = (SCREEN_W - w) * 0.5 - minx
    pad_y = (SCREEN_H - hud - h) * 0.52 - miny + hud * 0.35
    return IsoView(hw, hh, pad_x, pad_y, wall_h)


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


def draw_pending_wafer(surf: pygame.Surface, view: IsoView, col: int, row: int) -> None:
    cx, cy = view.center(float(col), float(row))
    cy -= view.hh * 0.15
    pygame.draw.ellipse(surf, (215, 220, 230), (int(cx - view.hw * 0.28), int(cy - view.hh * 0.12), int(view.hw * 0.56), int(view.hh * 0.38)))
    pygame.draw.ellipse(surf, (120, 125, 140), (int(cx - view.hw * 0.28), int(cy - view.hh * 0.12), int(view.hw * 0.56), int(view.hh * 0.38)), 1)
    pygame.draw.circle(surf, (255, 230, 140), (int(cx), int(cy - view.hh * 0.35)), int(view.hh * 0.22))


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
    cx, cy = view.center(float(col), float(row))
    bx = int(cx - view.hw * 0.9)
    by = int(cy - view.wall_h - view.hh * 2.2)
    bw = int(view.hw * 1.8)
    bh = 8
    pygame.draw.rect(surf, (28, 30, 38), (bx, by, bw, bh), border_radius=3)
    fw = max(2, int(bw * min(1.0, max(0.0, frac) / max(0.001, denom))))
    pygame.draw.rect(surf, bar_color, (bx, by, fw, bh), border_radius=3)
    pygame.draw.rect(surf, (90, 95, 110), (bx, by, bw, bh), 1, border_radius=3)
    cap = font.render(caption, True, (210, 215, 230))
    surf.blit(cap, (bx + bw // 2 - cap.get_width() // 2, by - cap.get_height() - 2))


def draw_players_iso(
    surf: pygame.Surface,
    view: IsoView,
    players: Sequence[Tuple[float, float, Tuple[int, int, int]]],
    carries: Optional[Sequence[bool]] = None,
) -> None:
    ordered = sorted(enumerate(players), key=lambda t: t[1][0] + t[1][1])
    for i, (col, row, rgb) in ordered:
        cx, cy = view.center(col, row)
        shadow_w, shadow_h = view.hw * 0.85, view.hh * 0.55
        pygame.draw.ellipse(
            surf,
            (24, 26, 34),
            (int(cx - shadow_w), int(cy - shadow_h * 0.2), int(2 * shadow_w), int(2 * shadow_h)),
        )
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


def draw_world_iso(
    surf: pygame.Surface,
    view: IsoView,
    cells: List[List[Cell]],
    highlights: Iterable[Tuple[int, int]],
    *,
    pending_wafer_tiles: Optional[List[Tuple[int, int]]] = None,
    world_progress_font: Optional[pygame.font.Font] = None,
    expected_step: Optional[Cell] = None,
    inv_prog: float = 0.0,
    ch_prog: float = 0.0,
) -> None:
    hl_set = set(highlights)
    pending = set(pending_wafer_tiles or [])

    for depth in range(COLS + ROWS - 1):
        for c in range(COLS):
            r = depth - c
            if not (0 <= r < ROWS):
                continue
            cell = cells[r][c]
            if cell == Cell.WALL:
                draw_wall_block(surf, view, c, r, cell_base_color(cell))
            else:
                draw_floor_tile(surf, view, c, r, cell, (c, r) in hl_set)

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
                draw_pending_wafer(surf, view, c, r)

    if world_progress_font is not None:
        if expected_step == Cell.PROBER_WAIT:
            for c, r in all_station_tiles(cells, Cell.PROBER_WAIT):
                draw_progress_above_tile(
                    surf,
                    view,
                    c,
                    r,
                    inv_prog,
                    INVENTORY_WAIT_S,
                    (110, 185, 255),
                    "Inventory",
                    world_progress_font,
                )
        if expected_step == Cell.TEST_CHAMBER:
            for c, r in all_station_tiles(cells, Cell.TEST_CHAMBER):
                draw_progress_above_tile(
                    surf,
                    view,
                    c,
                    r,
                    ch_prog,
                    CHAMBER_RUN_S,
                    (255, 150, 90),
                    "Testing",
                    world_progress_font,
                )
