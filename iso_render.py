"""Isometric-style floor tiles and extruded walls (pseudo-3D, Overcooked-like)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import pygame

from constants import COLS, ROWS, SCREEN_H, SCREEN_W
from kitchen import Cell


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
    hw, hh = 42.0, 24.0
    wall_h = 44.0
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
    from constants import FLOOR, WALL

    if cell == Cell.WALL:
        return WALL
    if cell == Cell.FLOOR:
        return FLOOR
    if cell == Cell.INGREDIENT_BIN:
        return (72, 118, 78)
    if cell == Cell.CHOP:
        return (142, 118, 82)
    if cell == Cell.STOVE:
        return (148, 62, 62)
    if cell == Cell.PLATE:
        return (188, 188, 198)
    if cell == Cell.SERVE:
        return (78, 118, 168)
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


def draw_floor_tile(
    surf: pygame.Surface,
    view: IsoView,
    col: int,
    row: int,
    cell: Cell,
    highlight: bool,
) -> None:
    poly = view.corners_floor(col, row)
    base = cell_base_color(cell)
    if cell == Cell.WALL:
        return
    light = _shade(base, 1.12) if (col + row) % 2 == 0 else _shade(base, 0.94)
    pygame.draw.polygon(surf, light, poly)
    pygame.draw.polygon(surf, (22, 24, 32), poly, 1)
    if highlight:
        pygame.draw.polygon(surf, (255, 228, 120), poly, 3)


def draw_players_iso(
    surf: pygame.Surface,
    view: IsoView,
    players: Sequence[Tuple[float, float, Tuple[int, int, int]]],
) -> None:
    """players: (col, row, rgb) — sorted back-to-front."""
    ordered = sorted(players, key=lambda p: p[0] + p[1])
    for col, row, rgb in ordered:
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


def draw_world_iso(
    surf: pygame.Surface,
    view: IsoView,
    cells: List[List[Cell]],
    highlights: Iterable[Tuple[int, int]],
) -> None:
    hl_set = set(highlights)
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
