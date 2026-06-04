"""Window size state — fixed 1280×760 game buffer; web letterboxes with uniform scale."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import pygame

from constants import SCREEN_H, SCREEN_W

IS_WEB = sys.platform == "emscripten"

if IS_WEB:
    WINDOW_FLAGS = 0
else:
    WINDOW_FLAGS = 0

_active_display: "DisplayState | None" = None


@dataclass
class WebScaler:
    """Uniform letterbox from the fixed game buffer onto the browser canvas."""

    logical_w: int = SCREEN_W
    logical_h: int = SCREEN_H
    canvas_w: int = SCREEN_W
    canvas_h: int = SCREEN_H
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0

    def update_canvas(self, w: int, h: int) -> None:
        self.canvas_w = max(w, 1)
        self.canvas_h = max(h, 1)
        sx = self.canvas_w / self.logical_w
        sy = self.canvas_h / self.logical_h
        self.scale = min(sx, sy)
        dw = self.logical_w * self.scale
        dh = self.logical_h * self.scale
        self.offset_x = (self.canvas_w - dw) * 0.5
        self.offset_y = (self.canvas_h - dh) * 0.5

    def to_logical(self, pos: tuple[int | float, int | float]) -> tuple[int, int]:
        x = (float(pos[0]) - self.offset_x) / self.scale
        y = (float(pos[1]) - self.offset_y) / self.scale
        x = max(0.0, min(float(self.logical_w - 1), x))
        y = max(0.0, min(float(self.logical_h - 1), y))
        return int(x), int(y)

    def finger_to_logical(self, nx: float, ny: float) -> tuple[float, float]:
        lx, ly = self.to_logical((nx * self.canvas_w, ny * self.canvas_h))
        return float(lx), float(ly)

    def blit_game(self, canvas: pygame.Surface, game: pygame.Surface) -> None:
        canvas.fill((12, 14, 18))
        dw = max(1, int(self.logical_w * self.scale))
        dh = max(1, int(self.logical_h * self.scale))
        if dw == game.get_width() and dh == game.get_height():
            canvas.blit(game, (int(self.offset_x), int(self.offset_y)))
        else:
            scaled = pygame.transform.smoothscale(game, (dw, dh))
            canvas.blit(scaled, (int(self.offset_x), int(self.offset_y)))


class DisplayState:
    """Logical size is always the design resolution."""

    def __init__(self, width: int = SCREEN_W, height: int = SCREEN_H) -> None:
        self.width = SCREEN_W
        self.height = SCREEN_H
        self.scaler = WebScaler() if IS_WEB else None
        self.canvas: pygame.Surface | None = None

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


def set_active_display(display: DisplayState) -> None:
    global _active_display
    _active_display = display


def logical_mouse_pos(pos: tuple[int | float, int | float]) -> tuple[int, int]:
    if _active_display is not None and _active_display.scaler is not None:
        return _active_display.scaler.to_logical(pos)
    return int(pos[0]), int(pos[1])


def apply_web_canvas_css() -> None:
    """Aspect-ratio viewport so browser zoom never squashes the canvas."""
    if not IS_WEB:
        return
    try:
        import platform

        doc = platform.document
        canvas = platform.window.canvas
        if doc is None:
            return

        wrapper_id = "psi-game-viewport"
        wrapper = doc.getElementById(wrapper_id)
        if wrapper is None:
            wrapper = doc.createElement("div")
            wrapper.id = wrapper_id
            parent = canvas.parentElement
            if parent is not None:
                parent.insertBefore(wrapper, canvas)
                wrapper.appendChild(canvas)

        wrapper.style.maxWidth = f"{SCREEN_W}px"
        wrapper.style.width = "100%"
        wrapper.style.aspectRatio = f"{SCREEN_W} / {SCREEN_H}"
        wrapper.style.margin = "0 auto"
        wrapper.style.display = "block"
        wrapper.style.position = "relative"
        wrapper.style.overflow = "hidden"

        style = canvas.style
        style.width = "100%"
        style.height = "100%"
        style.display = "block"
        style.margin = "0"
        style.imageRendering = "auto"

        if doc.body:
            doc.body.style.margin = "0"
            doc.body.style.background = "#0c0e12"
            doc.body.style.overflowX = "hidden"
    except Exception:
        pass


def apply_fixed_window_chrome() -> None:
    """Remove minimize, maximize, and resize border on Windows (keeps layout static)."""
    if sys.platform != "win32" or IS_WEB:
        return
    try:
        import ctypes

        hwnd = pygame.display.get_wm_info().get("window")
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        gwl_style = -16
        style = user32.GetWindowLongW(hwnd, gwl_style)
        style &= ~0x00020000  # WS_MINIMIZEBOX
        style &= ~0x00010000  # WS_MAXIMIZEBOX
        style &= ~0x00040000  # WS_THICKFRAME (drag-resize border)
        user32.SetWindowLongW(hwnd, gwl_style, style)
        swp_nomove = 0x0002
        swp_nosize = 0x0001
        swp_nozorder = 0x0004
        swp_framechanged = 0x0020
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            swp_nomove | swp_nosize | swp_nozorder | swp_framechanged,
        )
    except Exception:
        pass


def sync_display_from_screen(display: DisplayState, screen: pygame.Surface) -> None:
    if IS_WEB:
        return
    if WINDOW_FLAGS != 0:
        display.width, display.height = screen.get_size()


def create_game_surface(display: DisplayState) -> pygame.Surface:
    """Return the draw surface; on web this is a fixed off-screen 1280×760 buffer."""
    display.canvas = pygame.display.set_mode(display.size, WINDOW_FLAGS)
    if IS_WEB and display.scaler is not None:
        display.scaler.update_canvas(*display.canvas.get_size())
        apply_web_canvas_css()
        set_active_display(display)
        return pygame.Surface((SCREEN_W, SCREEN_H))
    apply_fixed_window_chrome()
    set_active_display(display)
    return display.canvas


def handle_video_resize(display: DisplayState, w: int, h: int) -> None:
    """Resize browser canvas; game logic stays 1280×760 with uniform letterbox."""
    if IS_WEB:
        sw, sh = max(320, w), max(480, h)
        display.canvas = pygame.display.set_mode((sw, sh), WINDOW_FLAGS)
        if display.scaler is not None:
            display.scaler.update_canvas(sw, sh)
        apply_web_canvas_css()
        return
    sw, sh = max(320, w), max(480, h)
    display.canvas = pygame.display.set_mode((sw, sh), WINDOW_FLAGS)
    display.width, display.height = sw, sh


def present_frame(display: DisplayState, game: pygame.Surface) -> None:
    if display.scaler is not None and display.canvas is not None:
        cw, ch = display.canvas.get_size()
        if cw != display.scaler.canvas_w or ch != display.scaler.canvas_h:
            display.scaler.update_canvas(cw, ch)
        display.scaler.blit_game(display.canvas, game)
    pygame.display.flip()
