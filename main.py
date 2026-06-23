"""
PSI Quantum–inspired wafer lab (single player, Overcooked-style flow).
WASD + Space, or on-screen buttons + Use. Finish wafers before the shift timer ends.
"""

from __future__ import annotations

import asyncio
import random
import sys
from typing import List, Optional

import pygame

from constants import (
    BG,
    CRYO_MAX_QUEUE,
    DEBUG_MAP_EDITOR,
    FPS,
    INVENTORY_WAIT_S,
    LAB_TECH,
    MAX_WAFER_QUEUE,
    SHIFT_SECONDS,
    SPAWN_MAX_S,
    SPAWN_MIN_S,
)
from display import (
    DisplayState,
    create_game_surface,
    handle_video_resize,
    logical_mouse_pos,
    present_frame,
)
from cryo_lab import (
    CryoStep,
    Cryostat,
    CryostatPhase,
    bond_table_station,
    cryo_default_map,
    cryo_focus_sample,
    cryo_interaction_hint,
    cryo_step_destination,
    cryostat_station,
    find_cryo_spawn,
    near_cryo_station,
    new_cryo_sample,
)
from cryo_render import draw_cryo_world
from cryo_layout import flush_cryo_layout_to_disk, get_cryo_layout, reload_cryo_layout
from dev_layout import flush_layout_to_disk, reload_layout
from map_editor import MapEditor
from game_assets import GameAssets, make_iso_view_for_background
from iso_render import draw_players_iso, draw_prober_and_players_depth_sorted, draw_world_iso
from lab import (
    RECIPE_WAFER,
    TEST_CYCLE,
    Cell,
    ChuckStandbyTracker,
    WaferOrder,
    default_map,
    find_walkable_spawn,
    bench_order_on_side,
    chuck_in_test,
    gameplay_focus_order,
    in_vicinity,
    in_vicinity_of_station,
    nearest_rack_side,
    refresh_map_from_layout,
    set_floor_layout,
    clear_floor_layout,
    chuck_occupied,
    resolve_load_side_for_player,
    player_near_step,
    player_near_zone_id,
    random_spawn_booth,
    random_test,
    step_destination,
    test_label,
    wafer_visible_on_operator,
)
from player import Player
from touch_controls import SoloTouch
from highscores import best_for_name, normalize_name, submit_score
from levels import LEVEL_COUNT, LEVELS
from ui import (
    blit_centered,
    draw_editor_toggle,
    draw_left_hud_panel,
    draw_menu_name_chip,
    draw_menu_highscores,
    draw_cryo_hud,
    draw_shift_hud,
    draw_standby_penalty_notices,
    draw_help_button,
    draw_help_overlay,
    help_button_rect,
    help_handle_event,
    help_overlay_rect,
    editor_toggle_rect,
)


def font(size: int) -> pygame.font.Font:
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    for name in ("segoeui", "segoe ui", "arial"):
        path = pygame.font.match_font(name, bold=True)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.SysFont("segoeui", size, bold=True)


def _pulse_space(keys, last: bool, tap: bool) -> tuple[bool, bool]:
    down = bool(keys[pygame.K_SPACE])
    p = (down and not last) or tap
    return down, p


def _menu_layout(sw: int, sh: int) -> tuple[pygame.Rect, pygame.Rect, list[pygame.Rect], pygame.Rect]:
    from game_assets import OPERATOR_COUNT

    card_w, card_h = 140, 180
    gap = 24
    total_w = OPERATOR_COUNT * card_w + (OPERATOR_COUNT - 1) * gap
    start_x = sw // 2 - total_w // 2
    card_y = max(150, sh // 2 - 118)
    cards = [
        pygame.Rect(start_x + i * (card_w + gap), card_y, card_w, card_h)
        for i in range(OPERATOR_COUNT)
    ]
    btn_w, btn_h = 220, 46
    btn_play = pygame.Rect(sw // 2 - btn_w // 2, card_y + card_h + 52, btn_w, btn_h)
    btn_quit = pygame.Rect(sw // 2 - btn_w // 2, btn_play.bottom + 10, btn_w, 38)
    scores_rect = pygame.Rect(sw - 210, 72, 188, 200)
    return btn_play, btn_quit, cards, scores_rect


async def run_menu(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display: DisplayState,
    assets: GameAssets,
    sticks: SoloTouch,
    f: pygame.font.Font,
    fs: pygame.font.Font,
) -> tuple[str, int, pygame.Surface, str]:
    from game_assets import OPERATOR_COUNT, OPERATOR_NAMES

    selected_op = 0
    player_name = OPERATOR_NAMES[0] if OPERATOR_NAMES else "Operator"
    name_active = False
    mx = my = 0
    help_open = False
    while True:
        clock.tick(60)
        await asyncio.sleep(0)
        sw, sh = screen.get_size()
        btn_play, btn_quit, op_cards, scores_rect = _menu_layout(sw, sh)
        help_btn = help_button_rect(sw, sh)
        help_panel = help_overlay_rect(sw, sh, f, fs, "menu") if help_open else None
        name_rect = pygame.Rect(
            op_cards[selected_op].x + 8,
            op_cards[selected_op].bottom - 34,
            op_cards[selected_op].width - 16,
            28,
        )
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit", selected_op, screen, player_name
            ho, consumed = help_handle_event(
                event, help_open=help_open, help_btn=help_btn, overlay=help_panel
            )
            if consumed:
                help_open = ho
                continue
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if help_open:
                    continue
                if name_rect.collidepoint(event.pos):
                    name_active = True
                else:
                    name_active = False
                for i, rect in enumerate(op_cards):
                    if rect.collidepoint(event.pos):
                        selected_op = i
                        if i < len(OPERATOR_NAMES):
                            player_name = OPERATOR_NAMES[i]
                if btn_play.collidepoint(event.pos):
                    return "continue", selected_op, screen, normalize_name(player_name)
                if btn_quit.collidepoint(event.pos):
                    return "quit", selected_op, screen, player_name
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if name_active:
                        name_active = False
                    else:
                        return "quit", selected_op, screen, player_name
                elif event.key == pygame.K_RETURN:
                    return "continue", selected_op, screen, normalize_name(player_name)
                elif event.key in (pygame.K_LEFT, pygame.K_a) and not name_active:
                    selected_op = (selected_op - 1) % OPERATOR_COUNT
                    if selected_op < len(OPERATOR_NAMES):
                        player_name = OPERATOR_NAMES[selected_op]
                elif event.key in (pygame.K_RIGHT, pygame.K_d) and not name_active:
                    selected_op = (selected_op + 1) % OPERATOR_COUNT
                    if selected_op < len(OPERATOR_NAMES):
                        player_name = OPERATOR_NAMES[selected_op]
                elif event.key == pygame.K_1 and not name_active:
                    selected_op = 0
                    if OPERATOR_NAMES:
                        player_name = OPERATOR_NAMES[0]
                elif event.key == pygame.K_2 and OPERATOR_COUNT > 1 and not name_active:
                    selected_op = 1
                    if len(OPERATOR_NAMES) > 1:
                        player_name = OPERATOR_NAMES[1]
                elif event.key == pygame.K_3 and OPERATOR_COUNT > 2 and not name_active:
                    selected_op = 2
                    if len(OPERATOR_NAMES) > 2:
                        player_name = OPERATOR_NAMES[2]
                elif event.key == pygame.K_4 and OPERATOR_COUNT > 3 and not name_active:
                    selected_op = 3
                    if len(OPERATOR_NAMES) > 3:
                        player_name = OPERATOR_NAMES[3]
                elif name_active:
                    if event.key == pygame.K_BACKSPACE:
                        player_name = player_name[:-1]
                    elif event.key == pygame.K_TAB:
                        name_active = False
                    elif event.unicode and event.unicode.isprintable() and len(player_name) < 24:
                        player_name += event.unicode

        screen.fill(BG)
        title = f.render("PSI Quantum", True, (240, 244, 252))
        screen.blit(title, (sw // 2 - title.get_width() // 2, 52))
        sub = fs.render("Wafer test shift", True, (130, 138, 158))
        screen.blit(sub, (sw // 2 - sub.get_width() // 2, 52 + title.get_height() + 6))

        for i, rect in enumerate(op_cards):
            active = i == selected_op
            hov = rect.collidepoint(mx, my)
            fill = (58, 72, 108) if active else ((50, 58, 78) if hov else (34, 38, 50))
            pygame.draw.rect(screen, fill, rect, border_radius=12)
            border = (255, 228, 120) if active else (90, 98, 118)
            pygame.draw.rect(screen, border, rect, 2 if active else 1, border_radius=12)
            preview = assets.operator_menu_portrait(i, sprite_h=112)
            px = rect.centerx - preview.get_width() // 2
            py = rect.centery - preview.get_height() // 2 - 8
            screen.blit(preview, (px, py))
            if active:
                draw_menu_name_chip(screen, name_rect, fs, name=player_name, active=name_active)
            else:
                op_name = OPERATOR_NAMES[i] if i < len(OPERATOR_NAMES) else f"Op {i + 1}"
                chip = pygame.Rect(rect.x + 8, rect.bottom - 34, rect.width - 16, 28)
                draw_menu_name_chip(screen, chip, fs, name=op_name, active=False, muted=True)

        draw_menu_highscores(screen, scores_rect, fs)

        draw_help_button(screen, help_btn, fs, hovered=help_btn.collidepoint(mx, my), active=help_open)
        if help_open and help_panel is not None:
            draw_help_overlay(screen, help_panel, f, fs, "menu")

        for rect, label, primary in (
            (btn_play, "Continue", True),
            (btn_quit, "Quit", False),
        ):
            hov = rect.collidepoint(mx, my)
            if primary:
                pygame.draw.rect(screen, (52, 68, 104) if hov else (42, 52, 78), rect, border_radius=10)
                pygame.draw.rect(screen, (210, 218, 235), rect, 2, border_radius=10)
                z = f.render(label, True, (245, 248, 255))
            else:
                z = fs.render(label, True, (150, 158, 175) if hov else (120, 128, 145))
            screen.blit(z, (rect.centerx - z.get_width() // 2, rect.centery - z.get_height() // 2))

        present_frame(display, screen)


def _level_select_layout(sw: int, sh: int) -> tuple[pygame.Rect, pygame.Rect, list[pygame.Rect]]:
    card_w, card_h = 220, 168
    gap = 40
    total_w = LEVEL_COUNT * card_w + (LEVEL_COUNT - 1) * gap
    start_x = sw // 2 - total_w // 2
    card_y = max(170, sh // 2 - 100)
    cards = [
        pygame.Rect(start_x + i * (card_w + gap), card_y, card_w, card_h)
        for i in range(LEVEL_COUNT)
    ]
    btn_w, btn_h = 200, 44
    btn_play = pygame.Rect(sw // 2 - btn_w // 2, card_y + card_h + 48, btn_w, btn_h)
    btn_back = pygame.Rect(sw // 2 - btn_w // 2, btn_play.bottom + 10, btn_w, 36)
    return btn_play, btn_back, cards


async def run_level_select(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display: DisplayState,
    operator: int,
    player_name: str,
    f: pygame.font.Font,
    fs: pygame.font.Font,
) -> tuple[str, int, pygame.Surface]:
    from game_assets import OPERATOR_NAMES

    op_label = OPERATOR_NAMES[operator] if operator < len(OPERATOR_NAMES) else f"Op {operator + 1}"
    selected = 0
    mx = my = 0
    help_open = False

    while True:
        clock.tick(60)
        await asyncio.sleep(0)
        sw, sh = screen.get_size()
        btn_play, btn_back, level_cards = _level_select_layout(sw, sh)
        help_btn = help_button_rect(sw, sh)
        help_panel = help_overlay_rect(sw, sh, f, fs, "level_select") if help_open else None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit", selected + 1, screen
            ho, consumed = help_handle_event(
                event, help_open=help_open, help_btn=help_btn, overlay=help_panel
            )
            if consumed:
                help_open = ho
                continue
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if help_open:
                    continue
                for i, rect in enumerate(level_cards):
                    if rect.collidepoint(event.pos):
                        selected = i
                if btn_play.collidepoint(event.pos):
                    return "play", selected + 1, screen
                if btn_back.collidepoint(event.pos):
                    return "back", selected + 1, screen
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "back", selected + 1, screen
                elif event.key == pygame.K_RETURN:
                    return "play", selected + 1, screen
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    selected = (selected - 1) % LEVEL_COUNT
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    selected = (selected + 1) % LEVEL_COUNT
                elif event.key == pygame.K_1 and LEVEL_COUNT >= 1:
                    selected = 0
                elif event.key == pygame.K_2 and LEVEL_COUNT >= 2:
                    selected = 1

        screen.fill(BG)
        title = f.render("Select level", True, (240, 244, 252))
        screen.blit(title, (sw // 2 - title.get_width() // 2, 52))
        who = fs.render(f"{op_label} · {player_name}", True, (130, 138, 158))
        screen.blit(who, (sw // 2 - who.get_width() // 2, 52 + title.get_height() + 8))

        for i, rect in enumerate(level_cards):
            level = LEVELS[i]
            active = i == selected
            hov = rect.collidepoint(mx, my)
            fill = (58, 72, 108) if active else ((50, 58, 78) if hov else (34, 38, 50))
            pygame.draw.rect(screen, fill, rect, border_radius=12)
            border = (255, 228, 120) if active else (90, 98, 118)
            pygame.draw.rect(screen, border, rect, 2 if active else 1, border_radius=12)
            num = f.render(f"Level {level.id}", True, (255, 228, 140) if active else (180, 188, 205))
            screen.blit(num, (rect.centerx - num.get_width() // 2, rect.y + 22))
            name = fs.render(level.title, True, (245, 248, 255) if active else (210, 216, 230))
            screen.blit(name, (rect.centerx - name.get_width() // 2, rect.y + 58))
            sub = fs.render(level.subtitle, True, (140, 148, 168))
            screen.blit(sub, (rect.centerx - sub.get_width() // 2, rect.y + 88))

        for rect, label, primary in (
            (btn_play, "Start", True),
            (btn_back, "Back", False),
        ):
            hov = rect.collidepoint(mx, my)
            if primary:
                pygame.draw.rect(screen, (52, 68, 104) if hov else (42, 52, 78), rect, border_radius=10)
                pygame.draw.rect(screen, (210, 218, 235), rect, 2, border_radius=10)
                z = f.render(label, True, (245, 248, 255))
            else:
                z = fs.render(label, True, (150, 158, 175) if hov else (120, 128, 145))
            screen.blit(z, (rect.centerx - z.get_width() // 2, rect.centery - z.get_height() // 2))

        draw_help_button(screen, help_btn, fs, hovered=help_btn.collidepoint(mx, my), active=help_open)
        if help_open and help_panel is not None:
            draw_help_overlay(screen, help_panel, f, fs, "level_select")

        present_frame(display, screen)


async def run_cryo_level(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display: DisplayState,
    assets: GameAssets,
    view,
    sticks: SoloTouch,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    operator: int = 0,
    player_name: str = "Operator",
) -> tuple[pygame.Surface, object]:
    """Cryo tester — bond table + cryostat cool/align/warm cycle."""
    from cryo_lab import CryoSample

    f_ui, f_small, f_btn = fonts
    f_world = font(14)
    reload_cryo_layout()
    set_floor_layout(get_cryo_layout())
    sw, sh = display.width, display.height
    assets.set_screen_size(sw, sh)
    view = make_iso_view_for_background(assets, sw, sh)
    cells = cryo_default_map()
    spawn_col, spawn_row = find_cryo_spawn(cells)
    player = Player(spawn_col, spawn_row)
    samples: List[CryoSample] = []
    cryostat = Cryostat()
    next_spawn = random.uniform(SPAWN_MIN_S, SPAWN_MAX_S)
    shift_left = float(SHIFT_SECONDS)
    samples_done = 0
    interact_cd = 0.0
    last_space = False
    pulse_t = 0.0
    map_editor = MapEditor(kind="cryo") if DEBUG_MAP_EDITOR else None
    editor_enabled = False
    toggle_rect = editor_toggle_rect(display.width, display.height)
    autosave_left = 0.0
    help_open = False

    running = True
    try:
        while running:
            dt = clock.tick(FPS) / 1000.0
            await asyncio.sleep(0)
            if not (map_editor is not None and editor_enabled) and not help_open:
                shift_left -= dt
            interact_cd = max(0.0, interact_cd - dt)
            pulse_t += dt

            sw, sh = display.width, display.height
            toggle_rect = editor_toggle_rect(sw, sh)
            help_btn = help_button_rect(sw, sh, reserve_editor=DEBUG_MAP_EDITOR)
            help_panel = help_overlay_rect(sw, sh, f_ui, f_small, "cryo") if help_open else None
            mx, my = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    handle_video_resize(display, event.w, event.h)
                    continue
                if event.type == pygame.QUIT:
                    if map_editor is not None:
                        map_editor.end_drag(commit=True)
                    flush_cryo_layout_to_disk()
                    running = False
                    continue
                ho, consumed = help_handle_event(
                    event, help_open=help_open, help_btn=help_btn, overlay=help_panel
                )
                if consumed:
                    help_open = ho
                    continue
                if (
                    map_editor is not None
                    and editor_enabled
                    and map_editor.handle_event(event, view, enabled=True)
                ):
                    cells = refresh_map_from_layout()
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if help_open:
                        help_open = False
                        continue
                    if map_editor is not None:
                        map_editor.end_drag(commit=True)
                    flush_cryo_layout_to_disk()
                    running = False
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if DEBUG_MAP_EDITOR and toggle_rect.collidepoint(logical_mouse_pos(event.pos)):
                        editor_enabled = not editor_enabled
                        if map_editor is not None:
                            map_editor.set_enabled(editor_enabled)
                        cells = refresh_map_from_layout()
                        continue
                if (
                    map_editor is not None
                    and event.type == pygame.KEYDOWN
                    and event.key == pygame.K_m
                ):
                    editor_enabled = map_editor.toggle()
                    cells = refresh_map_from_layout()
                    continue
                sticks.handle_event(event, ignore_mouse=editor_enabled or help_open)

            keys = pygame.key.get_pressed()
            lv = sticks.vector()
            dx = float(keys[pygame.K_d] - keys[pygame.K_a]) + lv[0]
            dy = float(keys[pygame.K_s] - keys[pygame.K_w]) + lv[1]
            tap = sticks.pop_use()
            last_space, pulse = _pulse_space(keys, last_space, tap)

            editing = (map_editor is not None and editor_enabled) or help_open
            if editing and map_editor is not None:
                autosave_left -= dt
                if autosave_left <= 0.0:
                    map_editor.persist()
                    autosave_left = 1.0
            if editing and map_editor is not None and map_editor.is_dragging:
                if pygame.mouse.get_pressed(num_buttons=3)[0]:
                    map_editor.continue_drag(view, logical_mouse_pos(pygame.mouse.get_pos()))
                    cells = refresh_map_from_layout()
                else:
                    map_editor.end_drag(commit=True)
                    cells = refresh_map_from_layout()

            if editing:
                cells = refresh_map_from_layout()
            else:
                player.update(cells, dx, dy, dt)
            player_moving = (dx != 0 or dy != 0) and not editing
            at_cryo = near_cryo_station(player.col, player.row, cryostat_station())
            if not editing:
                cryostat.tick(dt, player_at_cryostat=at_cryo)

            if not editing and pulse and interact_cd <= 0:
                carry_idx = player.carrying_order_idx
                if player.carrying_wafer and carry_idx is not None and 0 <= carry_idx < len(samples):
                    s = samples[carry_idx]
                    step = s.next_step()
                    bond = bond_table_station()
                    if step == CryoStep.BOND and near_cryo_station(player.col, player.row, bond):
                        if s.advance(CryoStep.BOND):
                            interact_cd = 0.25
                    elif (
                        step == CryoStep.CRYO_LOAD
                        and at_cryo
                        and cryostat.can_load()
                        and s.advance(CryoStep.CRYO_LOAD)
                    ):
                        cryostat.load_sample(carry_idx)
                        s.in_cryostat = True
                        player.carrying_wafer = False
                        player.carrying_order_idx = None
                        interact_cd = 0.25
                    elif (
                        step == CryoStep.OUTGOING
                        and in_vicinity_of_station(cells, player.col, player.row, Cell.FINISHED_RACK)
                        and s.advance(CryoStep.OUTGOING)
                    ):
                        player.carrying_wafer = False
                        player.carrying_order_idx = None
                        samples.pop(carry_idx)
                        samples_done += 1
                        interact_cd = 0.25
                elif not player.carrying_wafer:
                    if at_cryo:
                        if cryostat.phase == CryostatPhase.LOADED_WARM and cryostat.start_cooldown():
                            interact_cd = 0.25
                        elif cryostat.phase == CryostatPhase.COLD and cryostat.start_align():
                            interact_cd = 0.15
                        elif cryostat.phase == CryostatPhase.ALIGNED and cryostat.start_test():
                            interact_cd = 0.25
                        elif cryostat.phase == CryostatPhase.TEST_PASSED and cryostat.start_warmup():
                            interact_cd = 0.25
                        elif cryostat.phase == CryostatPhase.WARM_LOADED:
                            idx = cryostat.loaded_sample_idx
                            if idx is not None and 0 <= idx < len(samples) and cryostat.unload_sample():
                                s = samples[idx]
                                s.in_cryostat = False
                                if s.advance(CryoStep.CRYO_UNLOAD):
                                    player.carrying_wafer = True
                                    player.carrying_order_idx = idx
                                    interact_cd = 0.25
                    else:
                        for i, s in enumerate(samples):
                            if (
                                s.next_step() == CryoStep.INCOMING
                                and in_vicinity(player.col, player.row, s.spawn_booth)
                                and s.advance(CryoStep.INCOMING)
                            ):
                                player.carrying_wafer = True
                                player.carrying_order_idx = i
                                interact_cd = 0.25
                                break

            next_spawn -= dt
            if not editing and next_spawn <= 0 and len(samples) < CRYO_MAX_QUEUE:
                samples.append(new_cryo_sample())
                next_spawn = random.uniform(SPAWN_MIN_S, SPAWN_MAX_S)

            if shift_left <= 0:
                running = False

            screen.fill(BG if assets.background is None else (18, 20, 26))
            pending: List[tuple[int, int]] = []
            for s in samples:
                if s.next_step() == CryoStep.INCOMING:
                    pending.append(s.spawn_booth)

            objective_arrow = None
            focus = cryo_focus_sample(
                samples, cryostat, player.carrying_order_idx, player.col, player.row, cells
            )
            if focus is not None:
                dest = cryo_step_destination(
                    samples,
                    cryostat,
                    focus,
                    carrying=player.carrying_wafer,
                    cells=cells,
                )
                if dest is not None:
                    objective_arrow = (player.col, player.row, dest[0], dest[1], pulse_t)

            draw_cryo_world(
                screen,
                view,
                cells,
                assets,
                cryostat,
                samples,
                f_world,
                objective_arrow=objective_arrow,
                pending_tiles=pending,
                players=[(player.col, player.row, LAB_TECH)],
                carries=(player.carrying_wafer,),
                moving=(player_moving,),
                facings=(player.facing_right,),
                facing_mirrors=(player.facing_mirror,),
                operators=(operator,),
            )
            sticks.draw(screen, f_btn)

            hud_panel = draw_left_hud_panel(screen, sh)
            status: List[str] = []
            hint = cryo_interaction_hint(
                samples,
                cryostat,
                carrying_idx=player.carrying_order_idx,
                col=player.col,
                row=player.row,
                cells=cells,
            )
            if hint:
                status.append(hint)
            elif not samples:
                status.append("Waiting for incoming sample…")

            draw_cryo_hud(
                screen,
                hud_panel,
                (f_ui, f_small),
                shift_left=shift_left,
                samples_done=samples_done,
                samples=samples,
                cryostat=cryostat,
                status_lines=status or None,
            )
            if map_editor is not None:
                map_editor.draw(screen, view, f_world, enabled=editor_enabled)
            if DEBUG_MAP_EDITOR:
                draw_editor_toggle(screen, toggle_rect, enabled=editor_enabled, font=f_small)
            draw_help_button(
                screen,
                help_btn,
                f_small,
                hovered=help_btn.collidepoint(logical_mouse_pos((mx, my))),
                active=help_open,
            )
            if help_open and help_panel is not None:
                draw_help_overlay(screen, help_panel, f_ui, f_small, "cryo")
            blit_centered(screen, f_small, sh - 44, "WASD / D-pad · Space / Use · Esc = menu", (150, 155, 175))
            present_frame(display, screen)
    finally:
        if map_editor is not None:
            map_editor.end_drag(commit=True)
            if editor_enabled:
                map_editor.persist()
        flush_cryo_layout_to_disk()
        clear_floor_layout()

    t0 = 3.5
    name = normalize_name(player_name)
    is_new_best, _prev_best = submit_score(name, samples_done)
    personal_best = best_for_name(name)
    while t0 > 0:
        dt = clock.tick(60) / 1000.0
        await asyncio.sleep(0)
        t0 -= dt
        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                t0 = 0
        screen.fill(BG)
        sw, sh = screen.get_size()
        y = sh // 2 - 72
        msg = f"Shift over — {name}: {samples_done} samples"
        r = f_ui.render(msg, True, (240, 245, 255))
        screen.blit(r, (sw // 2 - r.get_width() // 2, y))
        y += r.get_height() + 12
        if is_new_best and samples_done > 0:
            sub = f_small.render("New personal best!", True, (255, 225, 140))
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, y))
        elif personal_best is not None:
            sub = f_small.render(f"Personal best: {personal_best}", True, (170, 180, 200))
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, y))
        present_frame(display, screen)

    return screen, view


async def run_shift(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display: DisplayState,
    view,
    sticks: SoloTouch,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    assets: GameAssets,
    operator: int = 0,
    player_name: str = "Operator",
) -> tuple[pygame.Surface, object]:
    f_ui, f_small, f_btn = fonts
    f_world = font(14)
    reload_layout()
    clear_floor_layout()
    sw, sh = display.width, display.height
    assets.set_screen_size(sw, sh)
    view = make_iso_view_for_background(assets, sw, sh)
    cells = default_map()
    spawn_col, spawn_row = find_walkable_spawn(cells)
    player = Player(spawn_col, spawn_row)
    orders: List[WaferOrder] = []
    next_spawn = random.uniform(SPAWN_MIN_S, SPAWN_MAX_S)
    shift_left = float(SHIFT_SECONDS)
    wafers_done = 0
    interact_cd = 0.0
    inv_prog = 0.0
    dial_by_side: dict[str, int] = {"l": 0, "r": 0}
    chuck_standby = ChuckStandbyTracker()
    last_space = False
    map_editor = MapEditor() if DEBUG_MAP_EDITOR else None
    editor_enabled = False
    toggle_rect = editor_toggle_rect(display.width, display.height)
    autosave_left = 0.0
    help_open = False

    running = True
    try:
      while running:
        dt = clock.tick(FPS) / 1000.0
        await asyncio.sleep(0)
        if not (map_editor is not None and editor_enabled) and not help_open:
            shift_left -= dt
        interact_cd = max(0.0, interact_cd - dt)

        sw, sh = display.width, display.height
        toggle_rect = editor_toggle_rect(sw, sh)
        help_btn = help_button_rect(sw, sh, reserve_editor=DEBUG_MAP_EDITOR)
        help_panel = help_overlay_rect(sw, sh, f_ui, f_small, "prober") if help_open else None
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.VIDEORESIZE:
                handle_video_resize(display, event.w, event.h)
                continue
            if event.type == pygame.QUIT:
                if map_editor is not None:
                    map_editor.end_drag(commit=True)
                flush_layout_to_disk()
                running = False
                continue
            ho, consumed = help_handle_event(
                event, help_open=help_open, help_btn=help_btn, overlay=help_panel
            )
            if consumed:
                help_open = ho
                continue
            if (
                map_editor is not None
                and editor_enabled
                and map_editor.handle_event(event, view, enabled=True)
            ):
                cells = refresh_map_from_layout()
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if help_open:
                    help_open = False
                    continue
                if map_editor is not None:
                    map_editor.end_drag(commit=True)
                flush_layout_to_disk()
                running = False
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if DEBUG_MAP_EDITOR and toggle_rect.collidepoint(logical_mouse_pos(event.pos)):
                    editor_enabled = not editor_enabled
                    if map_editor is not None:
                        map_editor.set_enabled(editor_enabled)
                    cells = refresh_map_from_layout()
                    continue
            if (
                map_editor is not None
                and event.type == pygame.KEYDOWN
                and event.key == pygame.K_m
            ):
                editor_enabled = map_editor.toggle()
                cells = refresh_map_from_layout()
                continue
            if event.type == pygame.KEYDOWN and orders and not (
                (map_editor is not None and editor_enabled) or help_open
            ):
                rack_side = nearest_rack_side(player.col, player.row)
                if rack_side is not None:
                    if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_COMMA):
                        dial_by_side[rack_side] = (dial_by_side[rack_side] - 1) % len(TEST_CYCLE)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_PERIOD):
                        dial_by_side[rack_side] = (dial_by_side[rack_side] + 1) % len(TEST_CYCLE)
            sticks.handle_event(event, ignore_mouse=editor_enabled or help_open)

        keys = pygame.key.get_pressed()
        lv = sticks.vector()
        dx = float(keys[pygame.K_d] - keys[pygame.K_a]) + lv[0]
        dy = float(keys[pygame.K_s] - keys[pygame.K_w]) + lv[1]
        tap = sticks.pop_use()
        last_space, pulse = _pulse_space(keys, last_space, tap)

        editing = (map_editor is not None and editor_enabled) or help_open
        if editing and map_editor is not None:
            autosave_left -= dt
            if autosave_left <= 0.0:
                map_editor.persist()
                autosave_left = 1.0
        if editing and map_editor is not None and map_editor.is_dragging:
            if pygame.mouse.get_pressed(num_buttons=3)[0]:
                map_editor.continue_drag(view, logical_mouse_pos(pygame.mouse.get_pos()))
                cells = refresh_map_from_layout()
            else:
                map_editor.end_drag(commit=True)
                cells = refresh_map_from_layout()

        if not editing:
            shift_left -= chuck_standby.tick(orders, dt)

        if not editing:
            player.update(cells, dx, dy, dt)
        player_moving = (dx != 0 or dy != 0) and not editing

        if editing:
            cells = refresh_map_from_layout()

        mhu_order: Optional[WaferOrder] = None
        rack_side_active = nearest_rack_side(player.col, player.row)
        if orders and not editing:
            for o in orders:
                if o.chamber_started:
                    o.tick_chamber(dt)
                elif o.next_expected() == Cell.TEST_CHAMBER and o.prober_side:
                    if player_near_step(
                        cells, player.col, player.row, o, Cell.TEST_CHAMBER, orders=orders
                    ):
                        o.start_chamber_run(orders)

            for o in orders:
                if o.next_expected() == Cell.PROBER_WAIT and player_near_step(
                    cells, player.col, player.row, o, Cell.PROBER_WAIT, orders=orders
                ):
                    mhu_order = o
                    break

            if mhu_order is not None:
                inv_prog += dt
                if inv_prog >= INVENTORY_WAIT_S:
                    mhu_order.force_advance(Cell.PROBER_WAIT)
                    inv_prog = 0.0
            else:
                inv_prog = 0.0

            carry_idx = player.carrying_order_idx
            if pulse and interact_cd <= 0:
                if player.carrying_wafer and carry_idx is not None and 0 <= carry_idx < len(orders):
                    o = orders[carry_idx]
                    exp = o.next_expected()
                    if exp == Cell.PROBER_LOAD and player_near_step(
                        cells, player.col, player.row, o, Cell.PROBER_LOAD, orders=orders
                    ):
                        load_side = resolve_load_side_for_player(
                            player.col, player.row, orders, o
                        )
                        if load_side is not None and o.apply_station(Cell.PROBER_LOAD):
                            o.prober_side = load_side
                            player.carrying_wafer = False
                            player.carrying_order_idx = None
                            interact_cd = 0.22
                    elif exp == Cell.FINISHED_RACK and player_near_step(
                        cells, player.col, player.row, o, Cell.FINISHED_RACK, orders=orders
                    ):
                        if o.apply_station(Cell.FINISHED_RACK):
                            player.carrying_wafer = False
                            player.carrying_order_idx = None
                            wafers_done += 1
                            orders.pop(carry_idx)
                            interact_cd = 0.22
                            dial_by_side = {"l": 0, "r": 0}
                elif not player.carrying_wafer:
                    for side in ("l", "r"):
                        bo = bench_order_on_side(orders, side, player.col, player.row)
                        if bo is None:
                            continue
                        if bo.prober_side is None:
                            if chuck_occupied(orders, side):
                                continue
                            bo.prober_side = side
                        if TEST_CYCLE[dial_by_side[side]] == bo.required:
                            if bo.apply_station(Cell.TEST_BENCH):
                                interact_cd = 0.22
                        else:
                            shift_left -= 2.0
                            interact_cd = 0.35
                        break
                    else:
                        for i, o in enumerate(orders):
                            if o.next_expected() == Cell.RECEIVING and player_near_step(
                                cells, player.col, player.row, o, Cell.RECEIVING, orders=orders
                            ):
                                if o.apply_station(Cell.RECEIVING):
                                    player.carrying_wafer = True
                                    player.carrying_order_idx = i
                                    interact_cd = 0.22
                                break
                        else:
                            for i, o in enumerate(orders):
                                if o.next_expected() == Cell.FINISHED_RACK and player_near_step(
                                    cells, player.col, player.row, o, Cell.PROBER_LOAD
                                ):
                                    player.carrying_wafer = True
                                    player.carrying_order_idx = i
                                    interact_cd = 0.22
                                    break

        if not editing:
            next_spawn -= dt
        if not editing and next_spawn <= 0 and len(orders) < MAX_WAFER_QUEUE:
            orders.append(WaferOrder(RECIPE_WAFER, random_test(), random_spawn_booth()))
            next_spawn = random.uniform(SPAWN_MIN_S, SPAWN_MAX_S)

        if not editing and shift_left <= 0:
            running = False

        screen.fill(BG if assets.background is None else (18, 20, 26))
        hl: List[tuple[int, int]] = []

        pending_wafers: List[tuple[int, int]] = []
        if not player.carrying_wafer:
            for o in orders:
                if o.next_expected() == Cell.RECEIVING:
                    pending_wafers.append(o.spawn_booth)

        objective_arrow = None
        focus = (
            gameplay_focus_order(orders, player.carrying_order_idx, cells, player.col, player.row)
            if orders
            else None
        )
        if focus is not None:
            exp_now = focus.next_expected()
            target = step_destination(cells, focus, carrying=player.carrying_wafer, orders=orders)
            if (
                target is not None
                and exp_now
                and not player_near_step(
                    cells, player.col, player.row, focus, exp_now, orders=orders
                )
            ):
                pulse_t = pygame.time.get_ticks() / 1000.0
                objective_arrow = (player.col, player.row, target[0], target[1], pulse_t)

        show_carry = player.carrying_wafer
        if show_carry and player.carrying_order_idx is not None:
            ci = player.carrying_order_idx
            if 0 <= ci < len(orders) and not wafer_visible_on_operator(orders[ci]):
                show_carry = False

        draw_world_iso(
            screen,
            view,
            cells,
            hl,
            pending_wafer_tiles=pending_wafers,
            world_progress_font=f_world,
            assets=assets,
            objective_arrow=objective_arrow,
            floor_debug=editor_enabled,
            orders=orders,
            dial_by_side=dial_by_side,
            bench_rack_side=rack_side_active,
            mhu_order=mhu_order,
            inv_prog=inv_prog,
            queue_count=0,
            ui_preview=editing,
        )
        draw_prober_and_players_depth_sorted(
            screen,
            view,
            assets,
            [(player.col, player.row, LAB_TECH)],
            (show_carry,),
            moving=(player_moving,),
            facings=(player.facing_right,),
            facing_mirrors=(player.facing_mirror,),
            operators=(operator,),
        )
        sticks.draw(screen, f_btn)

        if map_editor is not None:
            map_editor.draw(screen, view, f_world, enabled=editor_enabled)

        if DEBUG_MAP_EDITOR:
            draw_editor_toggle(screen, toggle_rect, enabled=editor_enabled, font=f_small)
        draw_help_button(
            screen,
            help_btn,
            f_small,
            hovered=help_btn.collidepoint(logical_mouse_pos((mx, my))),
            active=help_open,
        )
        if help_open and help_panel is not None:
            draw_help_overlay(screen, help_panel, f_ui, f_small, "prober")

        hud_panel = draw_left_hud_panel(screen, sh)
        rack_hud_side = rack_side_active
        rack_dial = None
        rack_required = None
        if rack_hud_side:
            bo = bench_order_on_side(orders, rack_hud_side, player.col, player.row)
            if bo:
                rack_dial = TEST_CYCLE[dial_by_side[rack_hud_side]]
                rack_required = bo.required
        status: List[str] = []
        if not orders:
            status.append("Waiting for wafer lot…")
        focus = (
            gameplay_focus_order(orders, player.carrying_order_idx, cells, player.col, player.row)
            if orders
            else None
        )
        if focus is not None:
            exp = focus.next_expected()
            if (
                exp == Cell.PROBER_LOAD
                and player.carrying_wafer
                and resolve_load_side_for_player(player.col, player.row, orders, focus) is None
                and chuck_occupied(orders, "l")
                and chuck_occupied(orders, "r")
            ):
                status.append("Stations busy")
            elif exp == Cell.FINISHED_RACK and not player.carrying_wafer:
                status.append("Pick up at load pad (Space)")
            elif exp == Cell.FINISHED_RACK:
                status.append("Rack at storage (Space)")
        draw_shift_hud(
            screen,
            hud_panel,
            (f_ui, f_small),
            shift_left=shift_left,
            wafers_done=wafers_done,
            orders=orders,
            rack_side=rack_hud_side,
            rack_dial=rack_dial,
            rack_required=rack_required,
            status_lines=status or None,
            chuck_tracker=chuck_standby,
            penalty_flash=bool(chuck_standby.notices),
        )
        draw_standby_penalty_notices(screen, (font(19), font(14)), chuck_standby.notices)

        hint = "WASD / D-pad · Space / Use · A/D = rack dial · Esc = menu"
        if DEBUG_MAP_EDITOR:
            hint += " · Editor / M"
        blit_centered(screen, f_small, sh - 44, hint, (150, 155, 175))
        present_frame(display, screen)

    finally:
        if map_editor is not None:
            map_editor.end_drag(commit=True)
            if editor_enabled:
                map_editor.persist()
        flush_layout_to_disk()

    t0 = 3.5
    name = normalize_name(player_name)
    is_new_best, _prev_best = submit_score(name, wafers_done)
    personal_best = best_for_name(name)
    while t0 > 0:
        dt = clock.tick(60) / 1000.0
        await asyncio.sleep(0)
        t0 -= dt
        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                t0 = 0
        screen.fill(BG)
        sw, sh = screen.get_size()
        y = sh // 2 - 72
        msg = f"Shift over — {name}: {wafers_done} wafers"
        r = f_ui.render(msg, True, (240, 245, 255))
        screen.blit(r, (sw // 2 - r.get_width() // 2, y))
        y += r.get_height() + 12
        if is_new_best and wafers_done > 0:
            sub = f_small.render("New personal best!", True, (255, 225, 140))
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, y))
        elif personal_best is not None:
            sub = f_small.render(f"Personal best: {personal_best}", True, (170, 180, 200))
            screen.blit(sub, (sw // 2 - sub.get_width() // 2, y))
        present_frame(display, screen)

    return screen, view


async def main() -> None:
    pygame.init()
    pygame.display.set_caption("PSI Quantum — wafer lab")
    display = DisplayState()
    screen = create_game_surface(display)
    clock = pygame.time.Clock()
    assets = GameAssets()
    assets.load()
    reload_layout()
    sw, sh = display.width, display.height
    assets.set_screen_size(sw, sh)
    view = make_iso_view_for_background(assets, sw, sh)
    sticks = SoloTouch(sw, sh, display=display)
    f_ui = font(28)
    f_small = font(21)
    f_btn = font(19)

    while True:
        choice, operator, screen, player_name = await run_menu(
            screen, clock, display, assets, sticks, f_ui, f_small
        )
        if choice == "quit":
            break

        level_choice, level_id, screen = await run_level_select(
            screen, clock, display, operator, player_name, f_ui, f_small
        )
        if level_choice == "quit":
            break
        if level_choice == "back":
            continue

        if level_id == 1:
            screen, view = await run_shift(
                screen,
                clock,
                display,
                view,
                sticks,
                (f_ui, f_small, f_btn),
                assets,
                operator,
                player_name,
            )
        elif level_id == 2:
            screen, view = await run_cryo_level(
                screen,
                clock,
                display,
                assets,
                view,
                sticks,
                (f_ui, f_small, f_btn),
                operator,
                player_name,
            )

    flush_layout_to_disk()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
