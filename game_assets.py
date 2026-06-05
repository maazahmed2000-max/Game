"""PSI Quantum lab art: background, operator sprites, prober cluster, wafer."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pygame

from constants import SCREEN_H, SCREEN_W, HUD_PANEL_WIDTH

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

FrameKey = Tuple[int, str]  # (operator_row, pose_name)

OPERATOR_HEIGHT_FACTOR = 7.0
PROBER_WIDTH_FACTOR = 15.5
OPERATOR_COUNT = 2
OPERATOR_NAMES: Tuple[str, ...] = ("Martin", "Katelyn")

WHITE_KEY = (255, 255, 255)
BLACK_KEY = (0, 0, 0)


def _has_transparent_pixels(surf: pygame.Surface, sample_step: int = 8) -> bool:
    w, h = surf.get_size()
    for y in range(0, h, sample_step):
        for x in range(0, w, sample_step):
            if surf.get_at((x, y))[3] < 200:
                return True
    return False


def _apply_colorkey(surf: pygame.Surface, rgb: Tuple[int, int, int]) -> pygame.Surface:
    """Sheets exported with a solid matte but no alpha channel."""
    keyed = surf.convert()
    keyed.set_colorkey(rgb)
    return keyed.convert_alpha()


def _load_rgba(
    path: Path,
    *,
    colorkey: Tuple[int, int, int] | None = None,
    key_black: bool | None = None,
) -> pygame.Surface:
    raw = pygame.image.load(path)
    if colorkey is not None:
        return _apply_colorkey(raw, colorkey)
    if key_black is None:
        probe = raw.convert_alpha()
        key_black = not _has_transparent_pixels(probe)
    if key_black:
        return _apply_colorkey(raw, BLACK_KEY)
    return raw.convert_alpha()


def _trim_visible(surf: pygame.Surface) -> pygame.Surface:
    mask = pygame.mask.from_surface(surf)
    rects = mask.get_bounding_rects()
    if not rects:
        return surf
    union = rects[0]
    for rect in rects[1:]:
        union = union.union(rect)
    return surf.subsurface(union).copy()


def _trim_operator_frame(surf: pygame.Surface) -> pygame.Surface:
    """Crop to the main sprite — ignore colorkey specks that widen the union bbox."""
    mask = pygame.mask.from_surface(surf)
    rects = mask.get_bounding_rects()
    if not rects:
        return surf
    if len(rects) == 1:
        return surf.subsurface(rects[0]).copy()
    main = max(rects, key=lambda r: r.width * r.height)
    return surf.subsurface(main).copy()


def _slice_operator_sheet(sheet: pygame.Surface) -> Dict[FrameKey, pygame.Surface]:
    w, h = sheet.get_size()
    cw, ch = w // 4, h // 2
    names = ("idle", "walk", "hold_idle", "hold_walk")
    out: Dict[FrameKey, pygame.Surface] = {}
    for row in range(2):
        for col, name in enumerate(names):
            rect = (col * cw, row * ch, cw, ch)
            frame = _trim_operator_frame(sheet.subsurface(rect).copy())
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
        self._screen_w = SCREEN_W
        self._screen_h = SCREEN_H
        self._bg_raw: pygame.Surface | None = None
        self._prober_cluster_cache: dict[int, pygame.Surface] = {}

    @property
    def world_rect(self) -> pygame.Rect:
        """Playable band to the right of the left HUD strip."""
        return pygame.Rect(
            HUD_PANEL_WIDTH,
            self.WORLD_TOP,
            max(320, self._screen_w - HUD_PANEL_WIDTH),
            self._screen_h - self.WORLD_TOP - self.FOOT_BAR,
        )

    def set_screen_size(self, width: int, height: int) -> None:
        self._screen_w = width
        self._screen_h = height
        self._scaled_cache.clear()
        self._prober_cluster_cache.clear()

    def align_background_to_view(self, view: "IsoView") -> None:
        """Pin background art to the prober anchor; scale locked to the iso view."""
        if self._bg_raw is None:
            return
        from lab import layout_camera_anchor

        ac, ar = layout_camera_anchor()
        sx, sy = view.center(ac, ar)
        wr = self.world_rect
        ref_hw = 36.0
        fit_scale = min(
            wr.width / self._bg_raw.get_width(),
            wr.height / self._bg_raw.get_height(),
        )
        scale = fit_scale * (view.hw / ref_hw)
        w = max(1, int(self._bg_raw.get_width() * scale))
        h = max(1, int(self._bg_raw.get_height() * scale))
        anchor_u, anchor_v = 0.48, 0.58
        bx = int(sx - w * anchor_u)
        by = int(sy - h * anchor_v)
        if bx < wr.x:
            bx = wr.x
        if by < wr.y:
            by = wr.y
        if bx + w > wr.right:
            bx = wr.right - w
        if by + h > wr.bottom:
            by = wr.bottom - h
        self.bg_rect = pygame.Rect(bx, by, w, h)
        self.background = pygame.transform.smoothscale(
            self._bg_raw, (w, h)
        ).convert_alpha()

    def load(self) -> None:
        if self._loaded:
            return
        self._bg_raw = _load_rgba(ASSETS_DIR / "background.png", colorkey=WHITE_KEY)
        self.bg_rect = pygame.Rect(0, 0, 0, 0)
        self.background = None

        stations_raw = _load_rgba(ASSETS_DIR / "stations.png", colorkey=WHITE_KEY)
        self.stations = _trim_visible(stations_raw)

        ops_l = _load_rgba(ASSETS_DIR / "operators.png", colorkey=WHITE_KEY)
        ops_r = _load_rgba(ASSETS_DIR / "operators_right.png", colorkey=WHITE_KEY)
        self._ops_left = _slice_operator_sheet(ops_l)
        self._ops_right = _slice_operator_sheet(ops_r)

        hold = self._ops_left[(0, "hold_idle")]
        self.wafer = _extract_wafer_from_hold(hold)

        self._loaded = True

    def operator_menu_portrait(self, operator: int, *, sprite_h: int = 150) -> pygame.Surface:
        """Title-screen card art — left-facing sheet (operators.png), not in-game right sheet."""
        op = max(0, min(OPERATOR_COUNT - 1, operator))
        cache_key = ("menu_portrait", op, sprite_h)
        if cache_key in self._scaled_cache:
            return self._scaled_cache[cache_key]
        frame = self._ops_left[(op, "idle")]
        scaled = _scale_to_height(frame, sprite_h)
        self._scaled_cache[cache_key] = scaled
        return scaled

    def operator_frame(
        self,
        operator: int,
        *,
        facing_right: bool,
        moving: bool,
        carrying: bool,
        sprite_h: int,
    ) -> pygame.Surface:
        operator = max(0, min(OPERATOR_COUNT - 1, operator))
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
        tw = int(max_width)
        if tw in self._prober_cluster_cache:
            img = self._prober_cluster_cache[tw]
        else:
            sw, sh = self.stations.get_size()
            th = max(1, int(sh * tw / sw))
            img = pygame.transform.smoothscale(self.stations, (tw, th)).convert_alpha()
            self._prober_cluster_cache[tw] = img
        cx, cy = int(center[0]), int(center[1])
        th = img.get_height()
        surf.blit(img, (cx - tw // 2, cy - th + int(th * 0.08)))


def make_iso_view_for_background(
    assets: GameAssets,
    screen_w: int | None = None,
    screen_h: int | None = None,
) -> "IsoView":
    """Fit the full floor grid in the playable area; pin background to the layout anchor."""
    from iso_render import _iso_view_in_rect

    sw = screen_w if screen_w is not None else assets._screen_w
    sh = screen_h if screen_h is not None else assets._screen_h
    assets.set_screen_size(sw, sh)
    view = _iso_view_in_rect(
        assets.world_rect,
        36.0,
        21.0,
        wall_h=40.0,
        vertical_bias=0.52,
    )
    assets.align_background_to_view(view)
    return view
