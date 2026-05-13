"""
PSI Quantum–inspired wafer lab (single player, Overcooked-style flow).
WASD + Space, or stick + Use. Finish wafers before the shift timer ends.
"""

from __future__ import annotations

import asyncio
import math
import random
import sys
from typing import List, Optional

import pygame

from constants import (
    BG,
    BUMP_RADIUS,
    BUMP_TIME_PENALTY,
    CHAMBER_RUN_S,
    COWORKER_COAT,
    FPS,
    INVENTORY_WAIT_S,
    LAB_TECH,
    SCREEN_H,
    SCREEN_W,
    SHIFT_SECONDS,
)
from coworker import Coworker
from iso_render import draw_players_iso, draw_world_iso, make_iso_view
from lab import (
    RECIPE_WAFER,
    TEST_CYCLE,
    Cell,
    WaferOrder,
    default_map,
    random_test,
    station_at,
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
            "Lab coat tech: receive silicon wafers, load the prober, wait for cassette inventory,",
            "set the correct test (E, O, EO, Oband, Cband, Other), run the chamber, rack finished lots.",
            "Bump a coworker or rush into equipment while holding a wafer — you drop it and lose shift time.",
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
) -> None:
    f_ui, f_small, f_btn = fonts
    cells = default_map()
    player = Player(2.0, 6.0)
    coworkers = [
        Coworker(5.2, 6.0, 9.0, 6.0, speed=1.0),
        Coworker(7.0, 2.2, 7.0, 7.8, speed=0.85),
    ]
    orders: List[WaferOrder] = []
    next_spawn = 2.0
    shift_left = float(SHIFT_SECONDS)
    wafers_done = 0
    interact_cd = 0.0
    bump_cd = 0.0
    inv_prog = 0.0
    ch_prog = 0.0
    dial_i = 0
    last_space = False
    bump_msg = ""
    bump_msg_t = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        await asyncio.sleep(0)
        shift_left -= dt
        interact_cd = max(0.0, interact_cd - dt)
        bump_cd = max(0.0, bump_cd - dt)
        bump_msg_t = max(0.0, bump_msg_t - dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN and orders:
                exp = orders[0].next_expected()
                pc, pr = player.center_tile()
                st = station_at(cells, pc, pr)
                if exp == Cell.TEST_BENCH and st == Cell.TEST_BENCH:
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
        for cw in coworkers:
            cw.update(cells, dt)

        if player.carrying_wafer and bump_cd <= 0:
            for cw in coworkers:
                d = math.hypot(player.col - cw.col, player.row - cw.row)
                if d < BUMP_RADIUS:
                    player.drop_wafer()
                    if orders:
                        orders.pop(0)
                    shift_left -= BUMP_TIME_PENALTY
                    bump_msg = f"Bumped a coworker — wafer lost and −{int(BUMP_TIME_PENALTY)} s on the clock"
                    bump_msg_t = 2.5
                    bump_cd = 1.0
                    inv_prog = ch_prog = 0.0
                    dial_i = 0
                    break

        if orders:
            o = orders[0]
            exp = o.next_expected()
            pc, pr = player.center_tile()
            st = station_at(cells, pc, pr)

            if exp == Cell.PROBER_WAIT and st == Cell.PROBER_WAIT:
                inv_prog += dt
                if inv_prog >= INVENTORY_WAIT_S:
                    o.force_advance(Cell.PROBER_WAIT)
                    inv_prog = 0.0
            else:
                inv_prog = 0.0

            if exp == Cell.TEST_CHAMBER and st == Cell.TEST_CHAMBER:
                ch_prog += dt
                if ch_prog >= CHAMBER_RUN_S:
                    o.force_advance(Cell.TEST_CHAMBER)
                    ch_prog = 0.0
            else:
                ch_prog = 0.0

            if pulse and interact_cd <= 0:
                if exp == Cell.RECEIVING and st == Cell.RECEIVING and not player.carrying_wafer:
                    if o.apply_station(Cell.RECEIVING):
                        player.carrying_wafer = True
                        interact_cd = 0.22
                elif exp == Cell.PROBER_LOAD and st == Cell.PROBER_LOAD and player.carrying_wafer:
                    if o.apply_station(Cell.PROBER_LOAD):
                        interact_cd = 0.22
                elif exp == Cell.TEST_BENCH and st == Cell.TEST_BENCH:
                    if TEST_CYCLE[dial_i] == o.required:
                        if o.apply_station(Cell.TEST_BENCH):
                            interact_cd = 0.22
                    else:
                        shift_left -= 2.0
                        interact_cd = 0.35
                elif exp == Cell.FINISHED_RACK and st == Cell.FINISHED_RACK and player.carrying_wafer:
                    if o.apply_station(Cell.FINISHED_RACK):
                        player.carrying_wafer = False
                        wafers_done += 1
                        orders.pop(0)
                        interact_cd = 0.22
                        dial_i = 0

        next_spawn -= dt
        if next_spawn <= 0 and len(orders) < 2:
            orders.append(WaferOrder(RECIPE_WAFER, random_test()))
            next_spawn = 10.0 + random.random() * 6.0

        if shift_left <= 0:
            running = False

        screen.fill(BG)
        hl = [player.center_tile()]
        draw_world_iso(screen, view, cells, hl)
        crew = [(player.col, player.row, LAB_TECH), *[(*cw.grid_pos(), COWORKER_COAT) for cw in coworkers]]
        carries = tuple([player.carrying_wafer] + [False] * len(coworkers))
        draw_players_iso(screen, view, crew, carries)
        sticks.draw(screen, f_btn)

        hud_y = 8
        screen.blit(f_ui.render(f"Shift time: {max(0, shift_left):.0f}s   |   Wafers completed: {wafers_done}", True, (235, 238, 250)), (12, hud_y))
        hud_y += 30
        if orders:
            o = orders[0]
            screen.blit(f_small.render(o.progress_text(), True, (255, 220, 170)), (12, hud_y))
            hud_y += 26
            exp = o.next_expected()
            pc, pr = player.center_tile()
            st = station_at(cells, pc, pr)
            if exp == Cell.PROBER_WAIT and st == Cell.PROBER_WAIT:
                w = int((SCREEN_W - 80) * min(1.0, inv_prog / INVENTORY_WAIT_S))
                pygame.draw.rect(screen, (50, 55, 70), (40, hud_y, SCREEN_W - 80, 14), border_radius=4)
                pygame.draw.rect(screen, (120, 180, 255), (40, hud_y, max(4, w), 14), border_radius=4)
                screen.blit(f_small.render("Prober inventory / cassette map…", True, (180, 200, 230)), (48, hud_y - 22))
            elif exp == Cell.TEST_CHAMBER and st == Cell.TEST_CHAMBER:
                w = int((SCREEN_W - 80) * min(1.0, ch_prog / CHAMBER_RUN_S))
                pygame.draw.rect(screen, (50, 55, 70), (40, hud_y, SCREEN_W - 80, 14), border_radius=4)
                pygame.draw.rect(screen, (255, 160, 90), (40, hud_y, max(4, w), 14), border_radius=4)
                screen.blit(f_small.render("Wafer under test…", True, (230, 190, 160)), (48, hud_y - 22))
            elif exp == Cell.TEST_BENCH and st == Cell.TEST_BENCH:
                cur = test_label(TEST_CYCLE[dial_i])
                screen.blit(
                    f_small.render(
                        f"Test bench: [{cur}]   ←/→ or A/D to change   Space when it matches {test_label(o.required)}",
                        True,
                        (160, 230, 200),
                    ),
                    (12, hud_y),
                )
        else:
            screen.blit(f_small.render("Waiting for incoming wafer lot…", True, (160, 165, 185)), (12, hud_y))

        if bump_msg_t > 0 and bump_msg:
            screen.blit(f_small.render(bump_msg, True, (255, 130, 130)), (12, SCREEN_H - 88))

        screen.blit(
            f_small.render("WASD move · Space / Use = interact · A/D cycle test · Esc = menu", True, (130, 135, 155)),
            (12, SCREEN_H - 44),
        )
        pygame.display.flip()

    # Brief result
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
    view = make_iso_view()
    sticks = SoloTouch(SCREEN_W, SCREEN_H)
    f_ui = font(22)
    f_small = font(17)
    f_btn = font(16)

    while True:
        choice = await run_menu(screen, clock, f_ui, f_small)
        if choice == "quit":
            break
        await run_shift(screen, clock, view, sticks, (f_ui, f_small, f_btn))

    pygame.quit()


asyncio.run(main())
