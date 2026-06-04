"""
PSI Quantum–inspired wafer lab (single player, Overcooked-style flow).
WASD + Space, or stick + Use. Finish wafers before the shift timer ends.
"""

from __future__ import annotations

import asyncio
import random
import sys
from typing import List, Optional

import pygame

from constants import (
    BG,
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
    WINDOW_FLAGS,
    create_game_surface,
    logical_mouse_pos,
    sync_display_from_screen,
)
from dev_layout import commit_layout, flush_layout_to_disk, get_layout, reload_layout
from map_editor import MapEditor
from game_assets import GameAssets, make_iso_view_for_background
from iso_render import draw_prober_and_players_depth_sorted, draw_world_iso
from lab import (
    RECIPE_WAFER,
    TEST_CYCLE,
    Cell,
    ChuckStandbyTracker,
    WaferOrder,
    default_map,
    find_walkable_spawn,
    bench_order_on_side,
    gameplay_focus_order,
    nearest_prober_side,
    nearest_rack_side,
    refresh_map_from_layout,
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
from ui import (
    blit_centered,
    draw_editor_toggle,
    draw_left_hud_panel,
    draw_shift_hud,
    draw_standby_penalty_notices,
    editor_toggle_rect,
)


def font(size: int) -> pygame.font.Font:
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    return pygame.font.SysFont("segoeui", size)


def _pulse_space(keys, last: bool, tap: bool) -> tuple[bool, bool]:
    down = bool(keys[pygame.K_SPACE])
    p = (down and not last) or tap
    return down, p


def _menu_layout(sw: int, sh: int) -> tuple[pygame.Rect, pygame.Rect, list[pygame.Rect]]:
    from game_assets import OPERATOR_COUNT

    btn_play = pygame.Rect(sw // 2 - 140, sh - 132, 280, 52)
    btn_quit = pygame.Rect(sw // 2 - 140, sh - 68, 280, 48)
    card_w, card_h = 200, 200
    gap = 48
    total_w = OPERATOR_COUNT * card_w + (OPERATOR_COUNT - 1) * gap
    start_x = sw // 2 - total_w // 2
    cards = [pygame.Rect(start_x + i * (card_w + gap), min(248, sh // 2 - 120), card_w, card_h) for i in range(OPERATOR_COUNT)]
    return btn_play, btn_quit, cards


async def run_menu(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display: DisplayState,
    assets: GameAssets,
    sticks: SoloTouch,
    f: pygame.font.Font,
    fs: pygame.font.Font,
) -> tuple[str, int, pygame.Surface]:
    from game_assets import OPERATOR_COUNT, OPERATOR_NAMES

    selected_op = 0
    mx = my = 0
    while True:
        clock.tick(60)
        await asyncio.sleep(0)
        sw, sh = screen.get_size()
        btn_play, btn_quit, op_cards = _menu_layout(sw, sh)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit", selected_op, screen
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, rect in enumerate(op_cards):
                    if rect.collidepoint(event.pos):
                        selected_op = i
                if btn_play.collidepoint(event.pos):
                    return "play", selected_op, screen
                if btn_quit.collidepoint(event.pos):
                    return "quit", selected_op, screen
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "quit", selected_op, screen
                if event.key == pygame.K_RETURN:
                    return "play", selected_op, screen
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    selected_op = (selected_op - 1) % OPERATOR_COUNT
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    selected_op = (selected_op + 1) % OPERATOR_COUNT
                if event.key == pygame.K_1:
                    selected_op = 0
                if event.key == pygame.K_2 and OPERATOR_COUNT > 1:
                    selected_op = 1

        screen.fill(BG)
        t = f.render("PSI Quantum — wafer test shift", True, (238, 242, 252))
        screen.blit(t, (sw // 2 - t.get_width() // 2, 56))
        lines = [
            "Receive at STORAGE, load the prober chuck, run MHU inventory at center, set test on side racks,",
            "probe on the station head, then rack finished lots.",
        ]
        y = 108
        for line in lines:
            s = fs.render(line, True, (170, 180, 200))
            screen.blit(s, (sw // 2 - s.get_width() // 2, y))
            y += 24

        pick = fs.render("Choose your operator", True, (200, 210, 230))
        screen.blit(pick, (sw // 2 - pick.get_width() // 2, op_cards[0].top - 34))

        for i, rect in enumerate(op_cards):
            active = i == selected_op
            hov = rect.collidepoint(mx, my)
            fill = (72, 92, 130) if active else ((62, 74, 102) if hov else (44, 52, 72))
            pygame.draw.rect(screen, fill, rect, border_radius=12)
            border = (255, 230, 140) if active else (200, 210, 235)
            pygame.draw.rect(screen, border, rect, 3 if active else 2, border_radius=12)
            preview = assets.operator_menu_portrait(i, sprite_h=150)
            px = rect.centerx - preview.get_width() // 2
            py = rect.centery - preview.get_height() // 2
            screen.blit(preview, (px, py))
            name = OPERATOR_NAMES[i] if i < len(OPERATOR_NAMES) else f"Operator {i + 1}"
            label = f.render(name, True, (245, 247, 255) if active else (210, 215, 230))
            screen.blit(label, (rect.centerx - label.get_width() // 2, rect.bottom + 10))

        hint = fs.render("Click a card or use ←/→ · keys 1–2 (Martin / Katelyn)", True, (140, 148, 168))
        screen.blit(hint, (sw // 2 - hint.get_width() // 2, op_cards[0].bottom + 38))

        for rect, label, big in (
            (btn_play, "Start shift", True),
            (btn_quit, "Quit", False),
        ):
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(screen, (58, 72, 110) if hov else (44, 52, 72), rect, border_radius=10)
            pygame.draw.rect(screen, (200, 210, 235), rect, 2, border_radius=10)
            fn = f if big else fs
            z = fn.render(label, True, (245, 247, 255))
            screen.blit(z, (rect.centerx - z.get_width() // 2, rect.centery - z.get_height() // 2))

        pygame.display.flip()


async def run_shift(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display: DisplayState,
    view,
    sticks: SoloTouch,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    assets: GameAssets,
    operator: int = 0,
) -> tuple[pygame.Surface, object]:
    f_ui, f_small, f_btn = fonts
    f_world = font(14)
    reload_layout()
    sync_display_from_screen(display, screen)
    sw, sh = screen.get_size()
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

    running = True
    try:
      while running:
        dt = clock.tick(FPS) / 1000.0
        await asyncio.sleep(0)
        shift_left -= dt
        interact_cd = max(0.0, interact_cd - dt)

        sw, sh = display.width, display.height
        toggle_rect = editor_toggle_rect(sw, sh)

        for event in pygame.event.get():
            if event.type == pygame.VIDEORESIZE:
                sw, sh = max(320, event.w), max(480, event.h)
                screen = pygame.display.set_mode((sw, sh), WINDOW_FLAGS)
                sync_display_from_screen(display, screen)
                assets.set_screen_size(sw, sh)
                sticks.set_screen_size(sw, sh)
                view = make_iso_view_for_background(assets, sw, sh)
                toggle_rect = editor_toggle_rect(sw, sh)
                cells = refresh_map_from_layout()
            elif event.type == pygame.QUIT:
                if map_editor is not None:
                    map_editor.end_drag(commit=True)
                flush_layout_to_disk()
                running = False
            elif (
                map_editor is not None
                and editor_enabled
                and map_editor.handle_event(event, view, enabled=True)
            ):
                cells = refresh_map_from_layout()
                continue
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if map_editor is not None:
                    map_editor.end_drag(commit=True)
                flush_layout_to_disk()
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if DEBUG_MAP_EDITOR and toggle_rect.collidepoint(logical_mouse_pos(event.pos)):
                    editor_enabled = not editor_enabled
                    if map_editor is not None:
                        map_editor.set_enabled(editor_enabled)
                    cells = refresh_map_from_layout()
            elif (
                map_editor is not None
                and event.type == pygame.KEYDOWN
                and event.key == pygame.K_m
            ):
                editor_enabled = map_editor.toggle()
                cells = refresh_map_from_layout()
            elif event.type == pygame.KEYDOWN and orders and not (
                map_editor is not None and editor_enabled
            ):
                rack_side = nearest_rack_side(player.col, player.row)
                if rack_side is not None:
                    if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_COMMA):
                        dial_by_side[rack_side] = (dial_by_side[rack_side] - 1) % len(TEST_CYCLE)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_PERIOD):
                        dial_by_side[rack_side] = (dial_by_side[rack_side] + 1) % len(TEST_CYCLE)
            sticks.handle_event(event, ignore_mouse=editor_enabled)

        keys = pygame.key.get_pressed()
        lv = sticks.vector()
        dx = float(keys[pygame.K_d] - keys[pygame.K_a]) + lv[0]
        dy = float(keys[pygame.K_s] - keys[pygame.K_w]) + lv[1]
        tap = sticks.pop_use()
        last_space, pulse = _pulse_space(keys, last_space, tap)

        editing = map_editor is not None and editor_enabled
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
                    if player_near_zone_id(player.col, player.row, f"chuck_{o.prober_side}"):
                        o.start_chamber_run()

            for o in orders:
                if o.next_expected() == Cell.PROBER_WAIT and player_near_step(
                    cells, player.col, player.row, o, Cell.PROBER_WAIT
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
                        cells, player.col, player.row, o, Cell.PROBER_LOAD
                    ):
                        if o.apply_station(Cell.PROBER_LOAD):
                            o.prober_side = nearest_prober_side(player.col, player.row, "load")
                            player.carrying_wafer = False
                            player.carrying_order_idx = None
                            interact_cd = 0.22
                    elif exp == Cell.FINISHED_RACK and player_near_step(
                        cells, player.col, player.row, o, Cell.FINISHED_RACK
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
                                cells, player.col, player.row, o, Cell.RECEIVING
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
            target = step_destination(cells, focus, carrying=player.carrying_wafer)
            if (
                target is not None
                and exp_now
                and not player_near_step(cells, player.col, player.row, focus, exp_now)
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
            operators=(operator,),
        )
        sticks.draw(screen, f_btn)

        if map_editor is not None:
            map_editor.draw(screen, view, f_world, enabled=editor_enabled)

        if DEBUG_MAP_EDITOR:
            draw_editor_toggle(screen, toggle_rect, enabled=editor_enabled, font=f_small)

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
            if exp == Cell.FINISHED_RACK and not player.carrying_wafer:
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
        draw_standby_penalty_notices(screen, (f_ui, f_small), chuck_standby.notices)

        hint = "WASD · Space = use · A/D = rack dial · Esc = menu"
        if DEBUG_MAP_EDITOR:
            hint += " · Editor / M"
        blit_centered(screen, f_small, sh - 44, hint, (130, 135, 155))
        pygame.display.flip()

    finally:
        if map_editor is not None:
            map_editor.end_drag(commit=True)
            if editor_enabled:
                map_editor.persist()
        flush_layout_to_disk()

    t0 = 2.5
    while t0 > 0:
        dt = clock.tick(60) / 1000.0
        await asyncio.sleep(0)
        t0 -= dt
        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                t0 = 0
        screen.fill(BG)
        msg = f"Shift over — wafers completed: {wafers_done}"
        r = f_ui.render(msg, True, (240, 245, 255))
        sw, sh = screen.get_size()
        screen.blit(r, (sw // 2 - r.get_width() // 2, sh // 2 - 40))
        pygame.display.flip()

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
    sync_display_from_screen(display, screen)
    sw, sh = screen.get_size()
    assets.set_screen_size(sw, sh)
    view = make_iso_view_for_background(assets, sw, sh)
    sticks = SoloTouch(sw, sh)
    f_ui = font(22)
    f_small = font(17)
    f_btn = font(16)

    while True:
        choice, operator, screen = await run_menu(screen, clock, display, assets, sticks, f_ui, f_small)
        if choice == "quit":
            break
        screen, view = await run_shift(
            screen,
            clock,
            display,
            view,
            sticks,
            (f_ui, f_small, f_btn),
            assets,
            operator,
        )

    flush_layout_to_disk()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
