"""
Kitchen Rush — online co-op: host creates a room; friend joins with username + code.
One player per device. Requires the FastAPI server (see server/).

Desktop: pip install -r requirements.txt && pip install -r server/requirements.txt
         uvicorn server.app:app --port 8765
         python main.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict

import pygame

from constants import API_BASE_URL, BG, FPS, PLAYER1, PLAYER2, SCREEN_H, SCREEN_W
from iso_render import draw_players_iso, draw_world_iso, make_iso_view
from kitchen import Cell, default_map
from lobby import GameSession, run_lobby
from net_client import ApiError, api_get, api_post
from touch_controls import SoloTouch


def font(size: int) -> pygame.font.Font:
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    return pygame.font.SysFont("segoeui", size)


async def run_game_network(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    view: Any,
    sticks: SoloTouch,
    session: GameSession,
    f_ui: pygame.font.Font,
    f_small: pygame.font.Font,
    f_btn: pygame.font.Font,
) -> None:
    cells: list[list[Cell]] = default_map()
    state: Dict[str, Any] = {
        "p1": {"c": 2.0, "r": 2.0},
        "p2": {"c": 5.0, "r": 2.0},
        "score": 0,
        "order_hud": "…",
        "p2_joined": session.me == 2,
        "names": {"1": "…", "2": "…"},
    }
    rid = session.room_id.upper()
    last_space = False
    input_acc = 0.0
    poll_acc = 0.0
    err_flash = ""
    pending_pulse = False

    running = True
    while running:
        ms = clock.tick(FPS)
        dt = ms / 1000.0
        input_acc += dt
        poll_acc += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            sticks.handle_event(event)

        keys = pygame.key.get_pressed()
        lv = sticks.vector()
        dx = float(keys[pygame.K_d] - keys[pygame.K_a]) + lv[0]
        dy = float(keys[pygame.K_s] - keys[pygame.K_w]) + lv[1]
        tap_use = sticks.pop_use()
        space_down = bool(keys[pygame.K_SPACE])
        pulse = (space_down and not last_space) or tap_use
        last_space = space_down
        if pulse:
            pending_pulse = True

        if input_acc >= 0.05:
            input_acc = 0.0
            pl = pending_pulse
            pending_pulse = False
            try:
                await api_post(
                    f"/api/rooms/{rid}/input",
                    {
                        "player": session.me,
                        "dx": dx,
                        "dy": dy,
                        "pulse_interact": pl,
                    },
                )
            except ApiError as e:
                err_flash = str(e)[:120]

        if poll_acc >= 0.05:
            poll_acc = 0.0
            try:
                state = await api_get(f"/api/rooms/{rid}/state")
            except ApiError as e:
                err_flash = str(e)[:120]

        p1c = float(state["p1"]["c"])
        p1r = float(state["p1"]["r"])
        p2c = float(state["p2"]["c"])
        p2r = float(state["p2"]["r"])
        score = int(state.get("score", 0))
        order_hud = str(state.get("order_hud", ""))
        n1 = str(state.get("names", {}).get("1", ""))
        n2 = str(state.get("names", {}).get("2", ""))

        screen.fill(BG)
        h1 = (int(round(p1c)), int(round(p1r)))
        h2 = (int(round(p2c)), int(round(p2r)))
        draw_world_iso(screen, view, cells, [h1, h2])
        draw_players_iso(
            screen,
            view,
            [
                (p1c, p1r, PLAYER1),
                (p2c, p2r, PLAYER2),
            ],
        )
        sticks.draw(screen, f_btn)

        hud_y = 8
        role = "You are host (P1)" if session.me == 1 else "You are guest (P2)"
        screen.blit(f_ui.render(f"Room {rid}  |  {role}", True, (220, 225, 240)), (12, hud_y))
        hud_y += 28
        screen.blit(f_small.render(f"{n1}  vs  {n2}  —  Score: {score}", True, (195, 200, 215)), (12, hud_y))
        hud_y += 26
        screen.blit(f_small.render(order_hud, True, (255, 210, 150)), (12, hud_y))
        hud_y += 26
        screen.blit(
            f_small.render("WASD + Space (or stick + Use)  |  Esc = leave match", True, (150, 155, 175)),
            (12, hud_y),
        )
        if err_flash:
            screen.blit(f_small.render(err_flash, True, (255, 120, 120)), (12, SCREEN_H - 40))

        pygame.display.flip()
        await asyncio.sleep(0)


async def main() -> None:
    pygame.init()
    pygame.display.set_caption("Kitchen Rush — online")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    view = make_iso_view()
    sticks = SoloTouch(SCREEN_W, SCREEN_H)

    f_ui = font(22)
    f_small = font(17)
    f_btn = font(16)

    while True:
        session = await run_lobby(screen, clock, f_ui, f_small)
        if session is None:
            break
        await run_game_network(screen, clock, view, sticks, session, f_ui, f_small, f_btn)

    pygame.quit()


asyncio.run(main())
