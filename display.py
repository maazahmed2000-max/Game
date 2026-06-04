"""Window size state — fixed game surface (no resize / minimize / maximize on desktop)."""

from __future__ import annotations

import sys

import pygame

from constants import SCREEN_H, SCREEN_W

# Web canvas may still resize with the page; desktop uses a locked 1280×760 window.
if sys.platform == "emscripten":
    WINDOW_FLAGS = pygame.RESIZABLE
else:
    WINDOW_FLAGS = 0


class DisplayState:
    """Logical size is always the design resolution on desktop."""

    def __init__(self, width: int = SCREEN_W, height: int = SCREEN_H) -> None:
        self.width = SCREEN_W if WINDOW_FLAGS == 0 else width
        self.height = SCREEN_H if WINDOW_FLAGS == 0 else height

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


def apply_fixed_window_chrome() -> None:
    """Remove minimize, maximize, and resize border on Windows (keeps layout static)."""
    if sys.platform != "win32" or WINDOW_FLAGS != 0:
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
    """On web/resizable windows, keep logical size in sync with the real surface."""
    if WINDOW_FLAGS != 0:
        display.width, display.height = screen.get_size()


def create_game_surface(display: DisplayState) -> pygame.Surface:
    screen = pygame.display.set_mode(display.size, WINDOW_FLAGS)
    sync_display_from_screen(display, screen)
    apply_fixed_window_chrome()
    return screen


def logical_mouse_pos(pos: tuple[int, int] | tuple[float, float]) -> tuple[int, int]:
    return int(pos[0]), int(pos[1])
