"""Shared HUD widgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import pygame

from constants import HUD_PANEL_WIDTH, HUD_PROGRESS_BAR_W

if TYPE_CHECKING:
    from lab import TestSpec, WaferOrder


def blit_centered(
    surf: pygame.Surface,
    font: pygame.font.Font,
    y: int,
    text: str,
    color: tuple[int, int, int],
) -> int:
    """Draw one centered line; returns Y below it."""
    line = font.render(text, True, color)
    surf.blit(line, (max(0, surf.get_width() // 2 - line.get_width() // 2), y))
    return y + line.get_height()


def draw_left_hud_panel(surf: pygame.Surface, height: int) -> pygame.Rect:
    """Dark strip on the left edge for readable HUD text."""
    panel = pygame.Rect(0, 0, HUD_PANEL_WIDTH, height)
    pygame.draw.rect(surf, (10, 12, 16), panel)
    pygame.draw.line(surf, (45, 52, 68), (panel.right - 1, 0), (panel.right - 1, height))
    return panel


def _left_x(panel: pygame.Rect, width: int) -> int:
    return panel.x + 12


def blit_left(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    text: str,
    color: tuple[int, int, int],
) -> int:
    line = font.render(text, True, color)
    surf.blit(line, (_left_x(panel, line.get_width()), y))
    return y + line.get_height()


def draw_editor_toggle(
    surf: pygame.Surface,
    rect: pygame.Rect,
    *,
    enabled: bool,
    font: pygame.font.Font,
) -> None:
    track = (52, 58, 72) if not enabled else (72, 110, 88)
    pygame.draw.rect(surf, track, rect, border_radius=rect.height // 2)
    pygame.draw.rect(surf, (190, 198, 215), rect, 1, border_radius=rect.height // 2)
    knob_r = rect.height - 6
    knob_x = rect.right - knob_r - 3 if enabled else rect.x + 3
    pygame.draw.circle(surf, (235, 240, 250), (knob_x, rect.centery), knob_r // 2)
    label = font.render("Editor", True, (220, 226, 240))
    surf.blit(label, (rect.x - label.get_width() - 8, rect.centery - label.get_height() // 2))


def editor_toggle_rect(screen_w: int, screen_h: int) -> pygame.Rect:
    del screen_h
    w, h = 44, 24
    return pygame.Rect(screen_w - 12 - w, 10, w, h)


def draw_hud_progress_bar(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    progress: float,
    *,
    caption: str,
    bar_color: tuple[int, int, int] = (120, 180, 255),
    width: int = HUD_PROGRESS_BAR_W,
) -> int:
    bar_h = 12
    bar_w = min(width, panel.width - 24)
    y = blit_left(surf, panel, font, y, caption, (200, 215, 235)) + 4
    x = _left_x(panel, bar_w)
    pygame.draw.rect(surf, (50, 55, 70), (x, y, bar_w, bar_h), border_radius=4)
    fw = max(4, int(bar_w * min(1.0, max(0.0, progress))))
    pygame.draw.rect(surf, bar_color, (x, y, fw, bar_h), border_radius=4)
    return y + bar_h + 8


def draw_rack_config_panel(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    side_label: str,
    dial_label: str,
    required_label: str,
) -> int:
    y = blit_left(surf, panel, font, y, f"{side_label} rack config", (180, 230, 200))
    y += 2
    y = blit_left(surf, panel, font, y, f"Dial: [{dial_label}]", (160, 230, 200))
    y += 2
    y = blit_left(
        surf,
        panel,
        font,
        y,
        f"Space when matches {required_label}",
        (140, 200, 180),
    )
    return y + 6


def draw_shift_hud(
    surf: pygame.Surface,
    panel: pygame.Rect,
    fonts: tuple[pygame.font.Font, pygame.font.Font],
    *,
    shift_left: float,
    wafers_done: int,
    orders: List["WaferOrder"],
    rack_side: Optional[str] = None,
    rack_dial: Optional["TestSpec"] = None,
    rack_required: Optional["TestSpec"] = None,
    mhu_progress: Optional[float] = None,
    status_lines: Optional[List[str]] = None,
) -> None:
    """Timer, queue, rack config, and status on the left border panel."""
    from lab import test_label

    f_ui, f_small = fonts
    y = 14
    if rack_side and rack_dial is not None and rack_required is not None:
        side_name = "Left" if rack_side == "l" else "Right"
        y = draw_rack_config_panel(
            surf,
            panel,
            f_small,
            y,
            side_name,
            test_label(rack_dial),
            test_label(rack_required),
        )
        y += 4
    y = blit_left(
        surf,
        panel,
        f_ui,
        y,
        f"Shift: {max(0, shift_left):.0f}s",
        (245, 248, 255),
    )
    y += 4
    y = blit_left(surf, panel, f_ui, y, f"Done: {wafers_done}", (220, 225, 240))
    y += 10
    n = len(orders)
    header = "Queue:" if n == 0 else (f"Queue ({n}):" if n > 1 else "Queue (1):")
    y = blit_left(surf, panel, f_small, y, header, (255, 230, 180))
    y += 4
    if not orders:
        y = blit_left(surf, panel, f_small, y, "  —", (200, 190, 160))
    else:
        for i, order in enumerate(orders):
            prefix = "▸ " if i == 0 else "  "
            side_tag = ""
            if order.prober_side:
                side_tag = f" ({order.prober_side.upper()} chuck)"
            y = blit_left(
                surf,
                panel,
                f_small,
                y,
                f"{prefix}{order.ticket_label()}{side_tag}",
                (255, 220, 170),
            )
            y += 2
    if mhu_progress is not None and mhu_progress > 0:
        y += 6
        y = draw_hud_progress_bar(
            surf,
            panel,
            f_small,
            y,
            mhu_progress,
            caption="MHU inventory…",
            width=panel.width - 24,
        )
    if status_lines:
        y += 6
        for line in status_lines:
            y = blit_left(surf, panel, f_small, y, line, (170, 180, 200))
            y += 2
