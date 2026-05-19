"""PSI Quantum lab art: background, operator sprites, prober cluster, wafer."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pygame

from constants import SCREEN_H, SCREEN_W

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

FrameKey = Tuple[int, str]  # (operator_row, pose_name)

OPERATOR_HEIGHT_FACTOR = 6.4
PROBER_WIDTH_FACTOR = 10.8


def _has_transparent_pixels(surf: pygame.Surface, sample_step: int = 8) -> bool:
    w, h = surf.get_size()
    for y in range(0, h, sample_step):
        for x in range(0, w, sample_step):
            if surf.get_at((x, y))[3] < 200:
                return True
    return False


def _apply_black_key(surf: pygame.Surface) -> pygame.Surface:
    """Sheets exported with a black matte but no alpha channel."""
    keyed = surf.convert()
    keyed.set_colorkey((0, 0, 0))
    return keyed.convert_alpha()


def _load_rgba(path: Path, *, key_black: bool | None = None) -> pygame.Surface:
    raw = pygame.image.load(path)
    if key_black is None:
        probe = raw.convert_alpha()
        key_black = not _has_transparent_pixels(probe)
    if key_black:
        return _apply_black_key(raw)
    return raw.convert_alpha()


def _trim_visible(surf: pygame.Surface) -> pygame.Surface:
    mask = pygame.mask.from_surface(surf)
    rects = mask.get_bounding_rects()
    if not rects:
        return surf
    return surf.subsurface(rects[0]).copy()


def _slice_operator_sheet(sheet: pygame.Surface) -> Dict[FrameKey, pygame.Surface]:
    w, h = sheet.get_size()
    cw, ch = w // 4, h // 2
    names = ("idle", "walk", "hold_idle", "hold_walk")
    out: Dict[FrameKey, pygame.Surface] = {}
    for row in range(2):
        for col, name in enumerate(names):
            rect = (col * cw, row * ch, cw, ch)
            frame = _trim_visible(sheet.subsurface(rect).copy())
            out[(row, name)] = frame
    return out


def _scale_to_height(surf: pygame.Surface, target_h: int) -> pygame.Surface:
    if target_h <= 0:
        return surf
    w, h = surf.get_size()
    if h == target_h:
        return surf
    nw = max(1, int(w * target_h / h))
    scaled = pygame.transform.smoothscale(surf, (nw, target_h))
    return scaled.convert_alpha()


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


def _extract_wafer_from_hold(hold: pygame.Surface) -> pygame.Surface:
    hw, hh = hold.get_width(), hold.get_height()
    crop = hold.subsurface(
        (int(hw * 0.42), int(hh * 0.18), max(1, int(hw * 0.42)), max(1, int(hh * 0.38)))
    ).copy()
    return _trim_visible(crop)


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
        self._scaled_cache: Dict[tuple, pygame.Surface] = {}
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

        stations_raw = _load_rgba(ASSETS_DIR / "stations.png")
        self.stations = _trim_visible(stations_raw)

        ops_l = _load_rgba(ASSETS_DIR / "operators.png", key_black=True)
        ops_r = _load_rgba(ASSETS_DIR / "operators_right.png", key_black=True)
        self._ops_left = _slice_operator_sheet(ops_l)
        self._ops_right = _slice_operator_sheet(ops_r)

        hold = self._ops_left[(0, "hold_idle")]
        self.wafer = _extract_wafer_from_hold(hold)

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
        cache_key = (operator, facing_right, pose, sprite_h)
        if cache_key in self._scaled_cache:
            return self._scaled_cache[cache_key]

        key: FrameKey = (operator, pose)
        sheet = self._ops_right if facing_right else self._ops_left
        scaled = _scale_to_height(sheet[key], sprite_h)
        self._scaled_cache[cache_key] = scaled
        return scaled

    def wafer_icon(self, size: int) -> pygame.Surface:
        assert self.wafer is not None
        cache_key = ("wafer", size)
        if cache_key in self._scaled_cache:
            return self._scaled_cache[cache_key]
        icon = _scale_to_height(self.wafer, size)
        self._scaled_cache[cache_key] = icon
        return icon

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
        img = pygame.transform.smoothscale(self.stations, (tw, th)).convert_alpha()
        cx, cy = int(center[0]), int(center[1])
        surf.blit(img, (cx - tw // 2, cy - th + int(th * 0.08)))


def make_iso_view_for_background(assets: GameAssets) -> "IsoView":
    """Same diamond grid as the original blueprint map, shifted onto the background art."""
    from iso_render import IsoView, make_iso_view

    base = make_iso_view()
    wr = assets.bg_rect
    anchor_col, anchor_row = 13.0, 10.0  # prober art anchor (not player spawn)
    floor_cx = wr.x + wr.width * 0.48
    floor_cy = wr.y + wr.height * 0.58
    ox = floor_cx - (anchor_col - anchor_row) * base.hw
    oy = floor_cy - (anchor_col + anchor_row) * base.hh
    return IsoView(base.hw, base.hh, ox, oy, base.wall_h)
