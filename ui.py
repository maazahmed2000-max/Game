"""Shared HUD widgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal, Optional, Tuple

import pygame

from constants import DEBUG_MAP_EDITOR, HUD_PANEL_WIDTH, HUD_PROGRESS_BAR_W

if TYPE_CHECKING:
    from cryo_lab import Cryostat, CryoSample
    from lab import ChuckStandbyTracker, StandbyPenaltyNotice, TestSpec, WaferOrder

HelpTopic = Literal["menu", "level_select", "prober", "cryo"]


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
    return panel.x + 10


def blit_left(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    text: str,
    color: tuple[int, int, int],
    *,
    shadow: bool = True,
) -> int:
    x = _left_x(panel, 0)
    if shadow:
        shadow_line = font.render(text, True, (0, 0, 0))
        surf.blit(shadow_line, (x + 1, y + 1))
    line = font.render(text, True, color)
    surf.blit(line, (x, y))
    return y + line.get_height() + 3


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
    bar_h = 16
    bar_w = min(width, panel.width - 28)
    y = blit_left(surf, panel, font, y, caption, (215, 225, 245)) + 6
    x = _left_x(panel, bar_w)
    pygame.draw.rect(surf, (50, 55, 70), (x, y, bar_w, bar_h), border_radius=4)
    fw = max(4, int(bar_w * min(1.0, max(0.0, progress))))
    pygame.draw.rect(surf, bar_color, (x, y, fw, bar_h), border_radius=4)
    return y + bar_h + 10


def draw_rack_config_panel(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    side_label: str,
    dial_label: str,
    required_label: str,
) -> int:
    y = blit_left(surf, panel, font, y, f"{side_label} rack config", (190, 240, 210))
    y += 4
    y = blit_left(surf, panel, font, y, f"Dial: [{dial_label}]", (175, 235, 205))
    y += 4
    y = blit_left(
        surf,
        panel,
        font,
        y,
        f"Space when matches {required_label}",
        (155, 210, 190),
    )
    return y + 8


def draw_chuck_status_panel(
    surf: pygame.Surface,
    panel: pygame.Rect,
    font: pygame.font.Font,
    y: int,
    orders: List["WaferOrder"],
    tracker: "ChuckStandbyTracker",
) -> int:
    from lab import ChuckStatus, chuck_status_for_side

    y = blit_left(surf, panel, font, y, "Chucks", (215, 225, 245))
    y += 4
    for side, name in (("l", "Left"), ("r", "Right")):
        status = chuck_status_for_side(orders, side)
        productive = status == ChuckStatus.PRODUCTIVE
        dot = (70, 220, 110) if productive else (245, 210, 80)
        label = "Productive" if productive else "Standby"
        line = f"  {name}: {label}"
        if not productive and tracker.armed:
            line += f" ({tracker.seconds_to_penalty(side):.0f}s)"
        x = _left_x(panel, 0)
        pygame.draw.circle(surf, dot, (x + 7, y + font.get_height() // 2), 6)
        y = blit_left(surf, panel, font, y, line, dot)
        y += 2
    return y + 6


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
    sw, sh = surf.get_size()
    y = sh - 200
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
        pad_x, pad_y = 10, 6
        bw = max(title_s.get_width(), detail_s.get_width()) + pad_x * 2
        bh = title_s.get_height() + detail_s.get_height() + pad_y * 2 + 2
        bx = sw // 2 - bw // 2
        bg_alpha = int(210 * fade)
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(bg, (48, 18, 18, bg_alpha), bg.get_rect(), border_radius=6)
        pygame.draw.rect(bg, (220, 90, 70, int(255 * fade)), bg.get_rect(), 1, border_radius=6)
        y -= bh
        surf.blit(bg, (bx, y))
        tx = sw // 2
        surf.blit(title_s, (tx - title_s.get_width() // 2, y + pad_y))
        surf.blit(
            detail_s,
            (tx - detail_s.get_width() // 2, y + pad_y + title_s.get_height() + 2),
        )
        y -= 6


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
    y = 6
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
        (255, 140, 120) if penalty_flash else (250, 252, 255),
    )
    y += 6
    y = blit_left(surf, panel, f_ui, y, f"Done: {wafers_done}", (230, 235, 248))
    y += 10
    if chuck_tracker is not None:
        y = draw_chuck_status_panel(surf, panel, f_small, y, orders, chuck_tracker)
    y += 2
    n = len(orders)
    header = "Queue:" if n == 0 else (f"Queue ({n}):" if n > 1 else "Queue (1):")
    y = blit_left(surf, panel, f_small, y, header, (255, 235, 190))
    y += 6
    if not orders:
        y = blit_left(surf, panel, f_small, y, "  —", (210, 200, 175))
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
                (255, 225, 175),
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
            y = blit_left(surf, panel, f_small, y, line, (185, 195, 215))
            y += 2


def draw_cryo_hud(
    surf: pygame.Surface,
    panel: pygame.Rect,
    fonts: tuple[pygame.font.Font, pygame.font.Font],
    *,
    shift_left: float,
    samples_done: int,
    samples: List["CryoSample"],
    cryostat: "Cryostat",
    status_lines: Optional[List[str]] = None,
) -> None:
    from cryo_lab import cryo_phase_label

    f_ui, f_small = fonts
    y = 6
    y = blit_left(surf, panel, f_ui, y, f"Shift: {max(0, shift_left):.0f}s", (250, 252, 255))
    y += 6
    y = blit_left(surf, panel, f_ui, y, f"Done: {samples_done}", (230, 235, 248))
    y += 8
    y = blit_left(surf, panel, f_small, y, "Cryostat", (180, 210, 255))
    y += 4
    y = blit_left(surf, panel, f_small, y, cryo_phase_label(cryostat.phase), (140, 190, 240))
    y += 8
    n = len(samples)
    header = "Queue:" if n == 0 else (f"Queue ({n}):" if n > 1 else "Queue (1):")
    y = blit_left(surf, panel, f_small, y, header, (255, 235, 190))
    y += 6
    if not samples:
        y = blit_left(surf, panel, f_small, y, "  —", (210, 200, 175))
    else:
        for i, sample in enumerate(samples):
            prefix = "▸ " if i == 0 else "  "
            tag = ""
            if sample.in_cryostat:
                tag = " (in cryo)"
            y = blit_left(
                surf,
                panel,
                f_small,
                y,
                f"{prefix}{sample.label}{tag}",
                (255, 225, 175),
            )
            y += 2
    if status_lines:
        y += 6
        for line in status_lines:
            y = blit_left(surf, panel, f_small, y, line, (185, 195, 215))
            y += 2


def draw_menu_name_chip(
    surf: pygame.Surface,
    rect: pygame.Rect,
    font: pygame.font.Font,
    *,
    name: str,
    active: bool = False,
    muted: bool = False,
) -> None:
    fill = (22, 26, 36) if not muted else (18, 20, 28)
    if active:
        fill = (36, 42, 58)
    pygame.draw.rect(surf, fill, rect, border_radius=6)
    if active:
        pygame.draw.rect(surf, (255, 228, 120), rect, 1, border_radius=6)
    text = name if name else " "
    cursor = "|" if active and (pygame.time.get_ticks() // 500) % 2 == 0 else ""
    color = (245, 248, 255) if not muted else (160, 168, 185)
    shown = font.render(text + cursor, True, color)
    surf.blit(shown, (rect.centerx - shown.get_width() // 2, rect.centery - shown.get_height() // 2))


def draw_menu_highscores(
    surf: pygame.Surface,
    rect: pygame.Rect,
    font: pygame.font.Font,
) -> None:
    from highscores import top_scores

    pygame.draw.rect(surf, (16, 18, 24), rect, border_radius=8)
    pygame.draw.rect(surf, (48, 54, 68), rect, 1, border_radius=8)
    y = rect.y + 10
    title = font.render("Best", True, (190, 198, 215))
    surf.blit(title, (rect.x + 12, y))
    y += title.get_height() + 8
    scores = top_scores(5)
    if not scores:
        return
    for i, entry in enumerate(scores):
        row = f"{i + 1}. {entry.name}  {entry.wafers}"
        color = (230, 210, 150) if i == 0 else (175, 182, 198)
        surf.blit(font.render(row, True, color), (rect.x + 12, y))
        y += font.get_height() + 3


_HELP_COPY: dict[HelpTopic, Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = {
    "menu": (
        "Operator select",
        (
            "Pick your operator (1–4 or click a card).",
            "Edit the name on the selected card if you like.",
            "Continue → choose a level.",
        ),
        (
            "Move: —",
            "1–4 / arrows: pick operator",
            "Enter: continue",
            "Esc: quit",
        ),
    ),
    "level_select": (
        "Level select",
        (
            "Level 1 — Room-temp prober test floor.",
            "Level 2 — Cryo hotplate + cryostat cycle.",
            "Finish as many lots as you can before time runs out.",
        ),
        (
            "1 / 2: pick level",
            "Arrows: change level",
            "Enter: start",
            "Esc: back to operators",
        ),
    ),
    "prober": (
        "Level 1 — Prober flow",
        (
            "1. Pick up wafer at incoming booth",
            "2. Load on prober chuck (free chuck only)",
            "3. Wait for cassette inventory at MHU",
            "4. Set test at rack (A/D) — match wafer recipe",
            "5. Run test chamber, then place in finished rack",
            "Idle chucks cost shift time after the first wafer arrives",
        ),
        (
            "WASD / D-pad: move",
            "Space / Use: interact",
            "A / D at rack: change test dial",
            "Esc: end shift (menu)",
        ),
    ),
    "cryo": (
        "Level 2 — Cryo flow",
        (
            "1. Pick up sample at incoming booth",
            "2. Bond on hotplate bonder",
            "3. Load in warm cryostat → start cooldown",
            "4. Hold Space at cryostat to align (when cold)",
            "5. Start quick test → start warm-up",
            "6. Remove sample → place in outgoing rack",
        ),
        (
            "WASD / D-pad: move",
            "Space / Use: interact / hold to align",
            "Esc: end shift (menu)",
        ),
    ),
}


def _help_editor_lines() -> Tuple[str, ...]:
    if not DEBUG_MAP_EDITOR:
        return ()
    return ("M / Editor toggle: map layout editor",)


def help_button_rect(screen_w: int, screen_h: int, *, reserve_editor: bool = False) -> pygame.Rect:
    """Small ? control — top-right; leaves room for Editor toggle when reserve_editor."""
    del screen_h
    size = 22
    x = screen_w - 12 - size
    if reserve_editor:
        x -= 44 + 6
    return pygame.Rect(x, 9, size, size)


def draw_help_button(
    surf: pygame.Surface,
    rect: pygame.Rect,
    font: pygame.font.Font,
    *,
    hovered: bool,
    active: bool,
) -> None:
    fill = (72, 110, 160) if active else ((58, 72, 104) if hovered else (42, 48, 62))
    pygame.draw.circle(surf, fill, rect.center, rect.width // 2)
    border = (255, 228, 120) if active else (140, 150, 170)
    pygame.draw.circle(surf, border, rect.center, rect.width // 2, 1)
    mark = font.render("?", True, (245, 248, 255))
    surf.blit(mark, (rect.centerx - mark.get_width() // 2, rect.centery - mark.get_height() // 2 - 1))


def help_overlay_rect(
    screen_w: int,
    screen_h: int,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    topic: HelpTopic,
) -> pygame.Rect:
    title, flow_lines, key_lines = _HELP_COPY[topic]
    editor_lines = _help_editor_lines()
    pad_x, pad_y = 22, 18
    line_h = body_font.get_height() + 4
    section_gap = 10
    inner_w = 420
    lines = 2 + len(flow_lines) + 1 + len(key_lines) + len(editor_lines) + 1
    inner_h = title_font.get_height() + section_gap + lines * line_h + pad_y * 2
    w = min(inner_w + pad_x * 2, screen_w - 24)
    h = min(inner_h, screen_h - 48)
    return pygame.Rect(screen_w // 2 - w // 2, screen_h // 2 - h // 2, w, h)


def draw_help_overlay(
    surf: pygame.Surface,
    panel: pygame.Rect,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    topic: HelpTopic,
) -> None:
    dim = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 150))
    surf.blit(dim, (0, 0))

    pygame.draw.rect(surf, (22, 26, 34), panel, border_radius=12)
    pygame.draw.rect(surf, (255, 228, 120), panel, 2, border_radius=12)

    title, flow_lines, key_lines = _HELP_COPY[topic]
    editor_lines = _help_editor_lines()
    x = panel.x + 20
    y = panel.y + 16
    t = title_font.render(title, True, (255, 228, 140))
    surf.blit(t, (x, y))
    y += t.get_height() + 12

    sec = body_font.render("Flow", True, (180, 200, 230))
    surf.blit(sec, (x, y))
    y += sec.get_height() + 6
    for line in flow_lines:
        surf.blit(body_font.render(line, True, (210, 218, 235)), (x, y))
        y += body_font.get_height() + 4

    y += 6
    sec = body_font.render("Keys", True, (180, 200, 230))
    surf.blit(sec, (x, y))
    y += sec.get_height() + 6
    for line in key_lines + editor_lines:
        surf.blit(body_font.render(line, True, (190, 198, 215)), (x, y))
        y += body_font.get_height() + 4

    hint = body_font.render("Click ? or Esc to close", True, (130, 138, 158))
    surf.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - hint.get_height() - 12))


def help_handle_event(
    event: pygame.event.Event,
    *,
    help_open: bool,
    help_btn: pygame.Rect,
    overlay: Optional[pygame.Rect],
) -> Tuple[bool, bool]:
    """Toggle or dismiss help. Returns (help_open, consumed)."""
    if event.type == pygame.KEYDOWN:
        if event.key in (pygame.K_h, pygame.K_F1):
            return (not help_open, True)
        if event.key == pygame.K_ESCAPE and help_open:
            return (False, True)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        pos = event.pos
        if help_btn.collidepoint(pos):
            return (not help_open, True)
        if help_open and overlay is not None and not overlay.collidepoint(pos):
            return (False, True)
    return (help_open, False)
