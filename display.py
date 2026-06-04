"""Window size state — fixed 1280×760; web lets the browser scale the canvas uniformly."""

from __future__ import annotations

import sys

import pygame

from constants import SCREEN_H, SCREEN_W

IS_WEB = sys.platform == "emscripten"

# Web: fixed internal resolution; CSS/browser zoom scales the whole canvas as one bitmap.
if IS_WEB:
    WINDOW_FLAGS = 0
else:
    WINDOW_FLAGS = 0

_active_display: "DisplayState | None" = None


class DisplayState:
    """Logical size is always the design resolution."""

    def __init__(self, width: int = SCREEN_W, height: int = SCREEN_H) -> None:
        self.width = SCREEN_W
        self.height = SCREEN_H
        self.canvas: pygame.Surface | None = None

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


def set_active_display(display: DisplayState) -> None:
    global _active_display
    _active_display = display


def logical_mouse_pos(pos: tuple[int, int] | tuple[float, float]) -> tuple[int, int]:
    return int(pos[0]), int(pos[1])


def apply_web_canvas_css() -> None:
    """Fit canvas in the page; browser zoom scales display size, not internal pixels."""
    if not IS_WEB:
        return
    try:
        import platform

        canvas = platform.window.canvas
        style = canvas.style
        style.width = "100%"
        style.height = "auto"
        style.maxWidth = f"{SCREEN_W}px"
        style.display = "block"
        style.margin = "0 auto"
        style.imageRendering = "auto"
        doc = platform.document
        if doc and doc.body:
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
    """Web keeps fixed logical size; desktop resizable windows may update dimensions."""
    if IS_WEB:
        return
    if WINDOW_FLAGS != 0:
        display.width, display.height = screen.get_size()


def create_game_surface(display: DisplayState) -> pygame.Surface:
    """Return the drawing surface (always 1280×760)."""
    display.canvas = pygame.display.set_mode(display.size, WINDOW_FLAGS)
    apply_web_canvas_css()
    apply_fixed_window_chrome()
    set_active_display(display)
    return display.canvas


def handle_video_resize(display: DisplayState, w: int, h: int) -> None:
    """Ignore browser zoom/resize on web — keep a fixed 1280×760 backing store."""
    if IS_WEB:
        display.canvas = pygame.display.set_mode(display.size, WINDOW_FLAGS)
        apply_web_canvas_css()
        return
    sw, sh = max(320, w), max(480, h)
    display.canvas = pygame.display.set_mode((sw, sh), WINDOW_FLAGS)
    display.width, display.height = sw, sh


def present_frame(display: DisplayState, game: pygame.Surface) -> None:
    """Present the frame (game surface is the canvas on web and desktop)."""
    del display, game
    pygame.display.flip()
