"""
Overcooked-style kitchen: isometric look, two players, touch sticks + use buttons.

Desktop: python main.py
Web (pygbag): run build_web.ps1, then open the test server URL or deploy build/web.
"""

from __future__ import annotations

import asyncio
import random
import sys
from typing import List

import pygame

from constants import BG, FPS, PLAYER1, PLAYER2, SCREEN_H, SCREEN_W
from iso_render import draw_players_iso, draw_world_iso, make_iso_view
from kitchen import Cell, Order, RECIPE_BURGER, default_map, station_at
from player import Player
from touch_controls import DualSticks


def font(size: int) -> pygame.font.Font:
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    return pygame.font.SysFont("segoeui", size)


async def main() -> None:
    pygame.init()
    pygame.display.set_caption("Kitchen Rush — co-op prototype")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    view = make_iso_view()
    sticks = DualSticks(SCREEN_W, SCREEN_H)

    cells = default_map()
    p1 = Player(2.0, 2.0)
    p2 = Player(5.0, 2.0)

    orders: List[Order] = []
    next_spawn = 2.5
    score = 0

    cd1 = 0.0
    cd2 = 0.0

    f_ui = font(22)
    f_small = font(17)
    f_btn = font(16)

    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        cd1 = max(0.0, cd1 - dt)
        cd2 = max(0.0, cd2 - dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            sticks.handle_event(event)

        keys = pygame.key.get_pressed()
        lv, rv = sticks.vectors()

        dx1 = float(keys[pygame.K_d] - keys[pygame.K_a]) + lv[0]
        dy1 = float(keys[pygame.K_s] - keys[pygame.K_w]) + lv[1]
        dx2 = float(keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) + rv[0]
        dy2 = float(keys[pygame.K_DOWN] - keys[pygame.K_UP]) + rv[1]

        p1.update(cells, dx1, dy1, dt)
        p2.update(cells, dx2, dy2, dt)

        tap1, tap2 = sticks.pop_interact()
        want1 = keys[pygame.K_SPACE] or tap1
        want2 = keys[pygame.K_RCTRL] or tap2

        def try_interact(player: Player, cd: float) -> float:
            nonlocal score
            if cd > 0 or not orders:
                return cd
            st = station_at(cells, *player.center_tile())
            if st is None:
                return cd
            for o in orders:
                if o.apply_station(st):
                    if o.is_done():
                        score += 10 + int(max(0, o.time_left))
                        orders.remove(o)
                    break
            return 0.22

        if want1:
            cd1 = try_interact(p1, cd1)
        if want2:
            cd2 = try_interact(p2, cd2)

        next_spawn -= dt
        if next_spawn <= 0 and len(orders) < 3:
            orders.append(Order(RECIPE_BURGER, time_left=45.0 + random.random() * 15))
            next_spawn = 8.0 + random.random() * 6.0

        for o in orders:
            o.time_left -= dt

        for o in [x for x in orders if x.time_left <= 0]:
            orders.remove(o)
            score = max(0, score - 5)

        screen.fill(BG)
        highlights = [p1.center_tile(), p2.center_tile()]
        draw_world_iso(screen, view, cells, highlights)
        draw_players_iso(
            screen,
            view,
            [
                (p1.col, p1.row, PLAYER1),
                (p2.col, p2.row, PLAYER2),
            ],
        )

        sticks.draw(screen, f_btn)

        hud_y = 10
        screen.blit(f_ui.render(f"Score: {score}", True, (240, 240, 245)), (16, hud_y))
        hud_y += 30
        screen.blit(
            f_small.render(
                "P1: WASD + Space   |   P2: Arrows + Right Ctrl   |   Touch: sticks + P1/P2 use",
                True,
                (195, 198, 210),
            ),
            (16, hud_y),
        )
        hud_y += 26
        if orders:
            o = orders[0]
            screen.blit(
                f_small.render(
                    f"Order: {o.progress_text()}  |  time {o.time_left:.0f}s",
                    True,
                    (255, 220, 160),
                ),
                (16, hud_y),
            )
        else:
            screen.blit(f_small.render("Waiting for orders…", True, (175, 178, 190)), (16, hud_y))

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


asyncio.run(main())
