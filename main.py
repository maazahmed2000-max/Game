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
    CHAMBER_RUN_S,
    FPS,
    INVENTORY_WAIT_S,
    LAB_TECH,
    SCREEN_H,
    SCREEN_W,
    SHIFT_SECONDS,
    SPAWN_MAX_S,
    SPAWN_MIN_S,
)
from game_assets import GameAssets, make_iso_view_for_background
from iso_render import draw_prober_and_players_depth_sorted, draw_world_iso
from lab import (
    RECIPE_WAFER,
    TEST_CYCLE,
    Cell,
    WaferOrder,
    default_map,
    find_walkable_spawn,
    player_near_step,
    prober_station_zones,
    random_spawn_booth,
    random_test,
    step_destination,
    test_label,
)
from player import Player
from touch_controls import SoloTouch


def font(size: int) -> pygame.font.Font:
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    return pygame.font.SysFont("segoeui", size)


def _pulse_space(keys, last: bool, tap: bool) -> tuple[bool, bool]:
    down = bool(keys[pygame.K_SPACE])
    p = (down and not last) or tap
    return down, p


async def run_menu(screen: pygame.Surface, clock: pygame.time.Clock, f: pygame.font.Font, fs: pygame.font.Font) -> str:
    btn_play = pygame.Rect(SCREEN_W // 2 - 140, 340, 280, 52)
    btn_quit = pygame.Rect(SCREEN_W // 2 - 140, 410, 280, 48)
    mx = my = 0
    while True:
        clock.tick(60)
        await asyncio.sleep(0)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_play.collidepoint(event.pos):
                    return "play"
                if btn_quit.collidepoint(event.pos):
                    return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                return "play"

        screen.fill(BG)
        t = f.render("PSI Quantum — wafer test shift", True, (238, 242, 252))
        screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 80))
        lines = [
            "Receive at STORAGE, load the prober chuck, run MHU inventory at center, set test on side racks,",
            "probe on the station head, then rack finished lots.",
            "New wafer lots arrive on a random schedule — watch the HUD and the glowing booth for the next pickup.",
        ]
        y = 140
        for line in lines:
            s = fs.render(line, True, (170, 180, 200))
            screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, y))
            y += 26

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
    view,
    sticks: SoloTouch,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    assets: GameAssets,
) -> None:
    f_ui, f_small, f_btn = fonts
    f_world = font(14)
    cells = default_map()
    spawn_col, spawn_row = find_walkable_spawn(cells)
    player = Player(spawn_col, spawn_row)
    orders: List[WaferOrder] = []
    next_spawn = random.uniform(SPAWN_MIN_S, SPAWN_MAX_S)
    shift_left = float(SHIFT_SECONDS)
    wafers_done = 0
    interact_cd = 0.0
    inv_prog = 0.0
    ch_prog = 0.0
    dial_i = 0
    last_space = False

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        await asyncio.sleep(0)
        shift_left -= dt
        interact_cd = max(0.0, interact_cd - dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN and orders:
                exp = orders[0].next_expected()
                if exp == Cell.TEST_BENCH and player_near_step(
                    cells, player.col, player.row, orders[0], Cell.TEST_BENCH
                ):
                    if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_COMMA):
                        dial_i = (dial_i - 1) % len(TEST_CYCLE)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_PERIOD):
                        dial_i = (dial_i + 1) % len(TEST_CYCLE)
            sticks.handle_event(event)

        keys = pygame.key.get_pressed()
        lv = sticks.vector()
        dx = float(keys[pygame.K_d] - keys[pygame.K_a]) + lv[0]
        dy = float(keys[pygame.K_s] - keys[pygame.K_w]) + lv[1]
        tap = sticks.pop_use()
        last_space, pulse = _pulse_space(keys, last_space, tap)

        player.update(cells, dx, dy, dt)
        player_moving = dx != 0 or dy != 0

        exp_for_bar: Optional[Cell] = None
        if orders:
            o = orders[0]
            exp = o.next_expected()
            exp_for_bar = exp
            near_step = player_near_step(cells, player.col, player.row, o, exp) if exp else False

            if exp == Cell.PROBER_WAIT and near_step:
                inv_prog += dt
                if inv_prog >= INVENTORY_WAIT_S:
                    o.force_advance(Cell.PROBER_WAIT)
                    inv_prog = 0.0
            else:
                inv_prog = 0.0

            if exp == Cell.TEST_CHAMBER and near_step:
                ch_prog += dt
                if ch_prog >= CHAMBER_RUN_S:
                    o.force_advance(Cell.TEST_CHAMBER)
                    ch_prog = 0.0
            else:
                ch_prog = 0.0

            if pulse and interact_cd <= 0:
                if exp == Cell.RECEIVING and near_step and not player.carrying_wafer:
                    if o.apply_station(Cell.RECEIVING):
                        player.carrying_wafer = True
                        interact_cd = 0.22
                elif exp == Cell.PROBER_LOAD and near_step and player.carrying_wafer:
                    if o.apply_station(Cell.PROBER_LOAD):
                        interact_cd = 0.22
                elif exp == Cell.TEST_BENCH and near_step:
                    if TEST_CYCLE[dial_i] == o.required:
                        if o.apply_station(Cell.TEST_BENCH):
                            interact_cd = 0.22
                    else:
                        shift_left -= 2.0
                        interact_cd = 0.35
                elif exp == Cell.FINISHED_RACK and near_step and player.carrying_wafer:
                    if o.apply_station(Cell.FINISHED_RACK):
                        player.carrying_wafer = False
                        wafers_done += 1
                        orders.pop(0)
                        interact_cd = 0.22
                        dial_i = 0

        next_spawn -= dt
        if next_spawn <= 0 and len(orders) < 2:
            orders.append(WaferOrder(RECIPE_WAFER, random_test(), random_spawn_booth()))
            next_spawn = random.uniform(SPAWN_MIN_S, SPAWN_MAX_S)

        if shift_left <= 0:
            running = False

        screen.fill(BG if assets.background is None else (18, 20, 26))
        pc, pr = player.center_tile()
        hl: List[tuple[int, int]] = [(pc, pr)]
        if orders and orders[0].next_expected() == Cell.RECEIVING and not player.carrying_wafer:
            hl.append(orders[0].spawn_booth)

        pending_wafers: List[tuple[int, int]] = []
        if orders and orders[0].next_expected() == Cell.RECEIVING and not player.carrying_wafer:
            pending_wafers.append(orders[0].spawn_booth)

        objective_arrow = None
        if orders:
            exp_now = orders[0].next_expected()
            if exp_now in (Cell.PROBER_WAIT, Cell.PROBER_LOAD, Cell.TEST_BENCH, Cell.TEST_CHAMBER):
                for z in prober_station_zones():
                    if z.step == exp_now:
                        hl.append((int(round(z.col)), int(round(z.row))))
            target = step_destination(cells, orders[0], carrying=player.carrying_wafer)
            if target is not None:
                hl.append(target)
                exp_now = orders[0].next_expected()
                if exp_now and not player_near_step(cells, player.col, player.row, orders[0], exp_now):
                    pulse_t = pygame.time.get_ticks() / 1000.0
                    objective_arrow = (player.col, player.row, target[0], target[1], pulse_t)

        rack_test = orders[0].required if orders else None
        bench_sel = TEST_CYCLE[dial_i] if orders and orders[0].next_expected() == Cell.TEST_BENCH else None

        draw_world_iso(
            screen,
            view,
            cells,
            hl,
            pending_wafer_tiles=pending_wafers,
            world_progress_font=f_world,
            expected_step=exp_for_bar,
            inv_prog=inv_prog,
            ch_prog=ch_prog,
            assets=assets,
            objective_arrow=objective_arrow,
            rack_test=rack_test,
            bench_selection=bench_sel,
        )
        draw_prober_and_players_depth_sorted(
            screen,
            view,
            assets,
            [(player.col, player.row, LAB_TECH)],
            (player.carrying_wafer,),
            moving=(player_moving,),
            facings=(player.facing_right,),
            operators=(0,),
        )
        sticks.draw(screen, f_btn)

        hud_y = 8
        screen.blit(
            f_ui.render(f"Shift time: {max(0, shift_left):.0f}s   |   Wafers completed: {wafers_done}", True, (235, 238, 250)),
            (12, hud_y),
        )
        hud_y += 30
        if orders:
            o = orders[0]
            screen.blit(f_small.render(o.progress_text(), True, (255, 220, 170)), (12, hud_y))
            hud_y += 26
            exp = o.next_expected()
            near = player_near_step(cells, player.col, player.row, o, exp) if exp else False
            if exp == Cell.PROBER_WAIT and near:
                w = int((SCREEN_W - 80) * min(1.0, inv_prog / INVENTORY_WAIT_S))
                pygame.draw.rect(screen, (50, 55, 70), (40, hud_y, SCREEN_W - 80, 14), border_radius=4)
                pygame.draw.rect(screen, (120, 180, 255), (40, hud_y, max(4, w), 14), border_radius=4)
                screen.blit(f_small.render("MHU inventory / cassette map…", True, (180, 200, 230)), (48, hud_y - 22))
            elif exp == Cell.TEST_CHAMBER and near:
                w = int((SCREEN_W - 80) * min(1.0, ch_prog / CHAMBER_RUN_S))
                pygame.draw.rect(screen, (50, 55, 70), (40, hud_y, SCREEN_W - 80, 14), border_radius=4)
                pygame.draw.rect(screen, (255, 160, 90), (40, hud_y, max(4, w), 14), border_radius=4)
                screen.blit(f_small.render("Wafer probing on station head…", True, (230, 190, 160)), (48, hud_y - 22))
            elif exp == Cell.TEST_BENCH and near:
                cur = test_label(TEST_CYCLE[dial_i])
                screen.blit(
                    f_small.render(
                        f"Config rack: [{cur}]   ←/→ or A/D to change   Space when it matches {test_label(o.required)}",
                        True,
                        (160, 230, 200),
                    ),
                    (12, hud_y),
                )
        else:
            screen.blit(f_small.render("Waiting for incoming wafer lot…", True, (160, 165, 185)), (12, hud_y))

        screen.blit(
            f_small.render("WASD move · Space / Use = interact · A/D cycle test · Esc = menu", True, (130, 135, 155)),
            (12, SCREEN_H - 44),
        )
        pygame.display.flip()

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
        screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2, SCREEN_H // 2 - 40))
        pygame.display.flip()


async def main() -> None:
    pygame.init()
    pygame.display.set_caption("PSI Quantum — wafer lab")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    assets = GameAssets()
    assets.load()
    view = make_iso_view_for_background(assets)
    sticks = SoloTouch(SCREEN_W, SCREEN_H)
    f_ui = font(22)
    f_small = font(17)
    f_btn = font(16)

    while True:
        choice = await run_menu(screen, clock, f_ui, f_small)
        if choice == "quit":
            break
        await run_shift(screen, clock, view, sticks, (f_ui, f_small, f_btn), assets)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
