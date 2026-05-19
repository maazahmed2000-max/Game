"""PSI Quantum lab art: background, operator sprites, prober cluster, wafer."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pygame

from constants import SCREEN_H, SCREEN_W

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

FrameKey = Tuple[int, str]  # (operator_row, pose_name)


def _slice_operator_sheet(sheet: pygame.Surface) -> Dict[FrameKey, pygame.Surface]:
    w, h = sheet.get_size()
    cw, ch = w // 4, h // 2
    names = ("idle", "walk", "hold_idle", "hold_walk")
    out: Dict[FrameKey, pygame.Surface] = {}
    for row in range(2):
        for col, name in enumerate(names):
            rect = (col * cw, row * ch, cw, ch)
            out[(row, name)] = sheet.subsurface(rect).copy()
    return out


def _scale_to_height(surf: pygame.Surface, target_h: int) -> pygame.Surface:
    if target_h <= 0:
        return surf
    w, h = surf.get_size()
    if h == target_h:
        return surf
    nw = max(1, int(w * target_h / h))
    return pygame.transform.smoothscale(surf, (nw, target_h))


def _fit_rect(src_w: int, src_h: int, dst: pygame.Rect) -> pygame.Rect:
    scale = min(dst.width / src_w, dst.height / src_h)
    w = int(src_w * scale)
    h = int(src_h * scale)
    return pygame.Rect(
        dst.x + (dst.width - w) // 2,
        dst.y + (dst.height - h) // 2,
        w,
        h,
    )


class GameAssets:
    """Loaded sprites; call ``load()`` after ``pygame.display.set_mode``."""

    WORLD_TOP = 98
    FOOT_BAR = 44

    def __init__(self) -> None:
        self.background: pygame.Surface | None = None
        self.bg_rect = pygame.Rect(0, 0, 0, 0)
        self.stations: pygame.Surface | None = None
        self.wafer: pygame.Surface | None = None
        self._ops_left: Dict[FrameKey, pygame.Surface] = {}
        self._ops_right: Dict[FrameKey, pygame.Surface] = {}
        self._loaded = False

    @property
    def world_rect(self) -> pygame.Rect:
        return pygame.Rect(
            0,
            self.WORLD_TOP,
            SCREEN_W,
            SCREEN_H - self.WORLD_TOP - self.FOOT_BAR,
        )

    def load(self) -> None:
        if self._loaded:
            return
        bg_raw = pygame.image.load(ASSETS_DIR / "background.png")
        self.bg_rect = _fit_rect(bg_raw.get_width(), bg_raw.get_height(), self.world_rect)
        self.background = pygame.transform.smoothscale(
            bg_raw, (self.bg_rect.width, self.bg_rect.height)
        )

        stations_raw = pygame.image.load(ASSETS_DIR / "stations.png").convert_alpha()
        self.stations = stations_raw

        ops_l = pygame.image.load(ASSETS_DIR / "operators.png").convert_alpha()
        ops_r = pygame.image.load(ASSETS_DIR / "operators_right.png").convert_alpha()
        self._ops_left = _slice_operator_sheet(ops_l)
        self._ops_right = _slice_operator_sheet(ops_r)

        hold = self._ops_left[(0, "hold_idle")]
        hw, hh = hold.get_width(), hold.get_height()
        wafer_rect = (int(hw * 0.52), int(hh * 0.28), int(hw * 0.34), int(hh * 0.32))
        self.wafer = hold.subsurface(wafer_rect).copy()

        self._loaded = True

    def operator_frame(
        self,
        operator: int,
        *,
        facing_right: bool,
        moving: bool,
        carrying: bool,
        sprite_h: int,
    ) -> pygame.Surface:
        pose = ("hold_walk" if moving else "hold_idle") if carrying else ("walk" if moving else "idle")
        key: FrameKey = (operator, pose)
        sheet = self._ops_right if facing_right else self._ops_left
        raw = sheet[key]
        return _scale_to_height(raw, sprite_h)

    def wafer_icon(self, size: int) -> pygame.Surface:
        assert self.wafer is not None
        return _scale_to_height(self.wafer, size)

    def draw_background(self, surf: pygame.Surface) -> None:
        if self.background is not None:
            surf.blit(self.background, self.bg_rect.topleft)

    def draw_prober_cluster(
        self,
        surf: pygame.Surface,
        center: Tuple[float, float],
        max_width: float,
    ) -> None:
        if self.stations is None:
            return
        sw, sh = self.stations.get_size()
        tw = int(max_width)
        th = max(1, int(sh * tw / sw))
        img = pygame.transform.smoothscale(self.stations, (tw, th))
        cx, cy = int(center[0]), int(center[1])
        surf.blit(img, (cx - tw // 2, cy - th + int(th * 0.12)))


def make_iso_view_for_background(assets: GameAssets) -> "IsoView":
    from iso_render import IsoView

    hw, hh = 34.0, 19.5
    wall_h = 34.0
    wr = assets.bg_rect
    # Align grid to the tiled floor (storage left, open center, SPADE right).
    floor_cx = wr.x + wr.width * 0.47
    floor_cy = wr.y + wr.height * 0.57
    anchor_col, anchor_row = 14.0, 6.0
    ox = floor_cx - (anchor_col - anchor_row) * hw
    oy = floor_cy - (anchor_col + anchor_row) * hh
    return IsoView(hw, hh, ox, oy, wall_h)
