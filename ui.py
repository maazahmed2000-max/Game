"""Shared HUD widgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import pygame

from constants import HUD_PANEL_WIDTH, HUD_PROGRESS_BAR_W

if TYPE_CHECKING:
    from lab import ChuckStandbyTracker, StandbyPenaltyNotice, TestSpec, WaferOrder


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


def draw_chuck_status_panel(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    orders: List["WaferOrder"],
    tracker: "ChuckStandbyTracker",
) -> int:
    from lab import ChuckStatus, chuck_status_for_side

    y = blit_left(surf, panel, font, y, "Chucks", (200, 210, 230))
    y += 2
    for side, name in (("l", "Left"), ("r", "Right")):
        status = chuck_status_for_side(orders, side)
        productive = status == ChuckStatus.PRODUCTIVE
        dot = (70, 210, 100) if productive else (235, 200, 70)
        label = "Productive" if productive else "Standby"
        line = f"  {name}: {label}"
        if not productive and tracker.armed:
            line += f" ({tracker.seconds_to_penalty(side):.0f}s)"
        x = _left_x(panel, 0)
        pygame.draw.circle(surf, dot, (x + 6, y + font.get_height() // 2), 5)
        y = blit_left(surf, panel, font, y, line, dot)
        y += 2
    return y + 4


def draw_standby_penalty_notices(
    surf: pygame.Surface,
    fonts: tuple[pygame.font.Font, pygame.font.Font],
    notices: List["StandbyPenaltyNotice"],
) -> None:
    """On-screen banner when a chuck standby penalty hits the shift timer."""
    if not notices:
        return

    from constants import CHUCK_STANDBY_NOTICE_S

    f_title, f_sub = fonts
    sw, _ = surf.get_size()
    y = 58
    for notice in notices:
        side_name = "Left" if notice.side == "l" else "Right"
        fade = min(1.0, max(0.0, notice.time_left / CHUCK_STANDBY_NOTICE_S))
        pulse = 0.85 + 0.15 * fade
        title = f"{side_name} chuck standby penalty"
        detail = f"−{notice.amount_s:.0f}s shift time"
        title_color = (
            int(255 * pulse),
            int(120 * pulse),
            int(100 * pulse),
        )
        detail_color = (255, int(210 * pulse), int(170 * pulse))

        title_s = f_title.render(title, True, title_color)
        detail_s = f_sub.render(detail, True, detail_color)
        pad_x, pad_y = 16, 10
        bw = max(title_s.get_width(), detail_s.get_width()) + pad_x * 2
        bh = title_s.get_height() + detail_s.get_height() + pad_y * 2 + 4
        bx = sw // 2 - bw // 2
        bg_alpha = int(210 * fade)
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(bg, (48, 18, 18, bg_alpha), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (220, 90, 70, int(255 * fade)), bg.get_rect(), 2, border_radius=8)
        surf.blit(bg, (bx, y))
        tx = sw // 2
        surf.blit(title_s, (tx - title_s.get_width() // 2, y + pad_y))
        surf.blit(
            detail_s,
            (tx - detail_s.get_width() // 2, y + pad_y + title_s.get_height() + 4),
        )
        y += bh + 8


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
    chuck_tracker: Optional["ChuckStandbyTracker"] = None,
    penalty_flash: bool = False,
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
        (255, 130, 110) if penalty_flash else (245, 248, 255),
    )
    y += 4
    y = blit_left(surf, panel, f_ui, y, f"Done: {wafers_done}", (220, 225, 240))
    y += 8
    if chuck_tracker is not None:
        y = draw_chuck_status_panel(surf, panel, f_small, y, orders, chuck_tracker)
    y += 2
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
