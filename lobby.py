"""Host / join lobby: create room or join with username + room code."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import pygame

from constants import BG, SCREEN_H, SCREEN_W
from net_client import ApiError, api_get, api_post


@dataclass
class GameSession:
    room_id: str
    me: int  # 1 = host, 2 = guest


def _draw_button(surf: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font, hover: bool) -> None:
    col = (70, 88, 130) if hover else (52, 60, 82)
    pygame.draw.rect(surf, col, rect, border_radius=8)
    pygame.draw.rect(surf, (200, 205, 230), rect, 2, border_radius=8)
    t = font.render(label, True, (240, 242, 250))
    surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))


def _text_edit(buf: str, max_len: int, event: pygame.event.Event) -> str:
    if event.type != pygame.KEYDOWN:
        return buf
    if event.key == pygame.K_BACKSPACE:
        return buf[:-1]
    ch = event.unicode
    if ch and ch.isprintable() and len(buf) < max_len:
        return buf + ch
    return buf


async def run_lobby(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    font: pygame.font.Font,
    font_small: pygame.font.Font,
) -> Optional[GameSession]:
    mode: Optional[str] = None
    host_name = "Chef"
    join_room = ""
    join_name = ""
    join_focus: str = "room"
    err_msg = ""
    room_waiting: Optional[str] = None
    poll_acc = 0.0

    btn_host = pygame.Rect(SCREEN_W // 2 - 200, 220, 400, 52)
    btn_join = pygame.Rect(SCREEN_W // 2 - 200, 290, 400, 52)
    btn_create = pygame.Rect(SCREEN_W // 2 - 120, 430, 240, 48)
    btn_go = pygame.Rect(SCREEN_W // 2 - 100, 540, 200, 48)
    rect_room = pygame.Rect(SCREEN_W // 2 - 200, 350, 400, 40)
    rect_name = pygame.Rect(SCREEN_W // 2 - 200, 430, 400, 40)

    mx = my = 0

    while True:
        ms = clock.tick(60)
        await asyncio.sleep(0)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if mode == "join_form":
                    if rect_room.collidepoint(event.pos):
                        join_focus = "room"
                    elif rect_name.collidepoint(event.pos):
                        join_focus = "name"

                if mode is None:
                    if btn_host.collidepoint(event.pos):
                        mode = "host_form"
                        err_msg = ""
                    elif btn_join.collidepoint(event.pos):
                        mode = "join_form"
                        err_msg = ""
                elif mode == "host_form" and btn_create.collidepoint(event.pos):
                    err_msg = ""
                    try:
                        data = await api_post("/api/rooms", {"host_name": (host_name.strip() or "Chef")[:18]})
                        room_waiting = str(data["room_id"])
                        mode = "host_wait"
                    except ApiError as e:
                        err_msg = str(e)[:220]
                elif mode == "join_form" and btn_go.collidepoint(event.pos):
                    rid = join_room.strip().upper().replace(" ", "")
                    nm = (join_name.strip() or "Guest")[:18]
                    if len(rid) < 4:
                        err_msg = "Enter the room code from the host."
                    else:
                        try:
                            await api_post(f"/api/rooms/{rid}/join", {"username": nm})
                            return GameSession(room_id=rid, me=2)
                        except ApiError as e:
                            err_msg = str(e)[:220]

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if mode in ("host_wait", "host_form", "join_form"):
                        mode = None
                        room_waiting = None
                        err_msg = ""
                    else:
                        return None
                elif mode == "host_form":
                    host_name = _text_edit(host_name, 18, event)
                elif mode == "join_form":
                    if join_focus == "room":
                        join_room = _text_edit(join_room, 10, event).upper()
                    else:
                        join_name = _text_edit(join_name, 18, event)

        if mode == "host_wait" and room_waiting:
            poll_acc += ms / 1000.0
            if poll_acc >= 0.35:
                poll_acc = 0.0
                try:
                    st = await api_get(f"/api/rooms/{room_waiting}/state")
                    if st.get("p2_joined"):
                        return GameSession(room_id=room_waiting, me=1)
                except ApiError:
                    err_msg = "Lost connection to server."

        screen.fill(BG)
        y = 36
        screen.blit(font.render("Kitchen Rush — online co-op", True, (235, 238, 250)), (SCREEN_W // 2 - 200, y))
        y += 48
        screen.blit(
            font_small.render(
                "Not GitHub login — use your Pages URL (.github.io). First open may show “Downloading…” for up to ~1 min.",
                True,
                (155, 175, 210),
            ),
            (SCREEN_W // 2 - 420, y),
        )
        y += 28
        screen.blit(
            font_small.render("One device = one chef; a friend joins from their phone with your room code.", True, (170, 176, 195)),
            (SCREEN_W // 2 - 380, y),
        )

        if mode is None:
            _draw_button(screen, btn_host, "Host game (get room code)", font_small, btn_host.collidepoint(mx, my))
            _draw_button(screen, btn_join, "Join friend (nickname + room code)", font_small, btn_join.collidepoint(mx, my))
        elif mode == "host_form":
            screen.blit(font_small.render("Your name (host):", True, (210, 215, 230)), (SCREEN_W // 2 - 200, 340))
            pygame.draw.rect(screen, (40, 44, 58), pygame.Rect(SCREEN_W // 2 - 200, 368, 400, 40), border_radius=6)
            screen.blit(font_small.render(host_name + "|", True, (245, 245, 250)), (SCREEN_W // 2 - 190, 376))
            _draw_button(screen, btn_create, "Create & wait for friend", font_small, btn_create.collidepoint(mx, my))
        elif mode == "host_wait" and room_waiting:
            screen.blit(font_small.render("Tell your friend this room code:", True, (210, 215, 230)), (SCREEN_W // 2 - 260, 340))
            rw = font.render(room_waiting, True, (255, 220, 120))
            screen.blit(rw, (SCREEN_W // 2 - rw.get_width() // 2, 380))
            screen.blit(font_small.render("Waiting for them to join…  (Esc = back)", True, (160, 165, 185)), (SCREEN_W // 2 - 220, 460))
        elif mode == "join_form":
            screen.blit(font_small.render("Room code (from host):", True, (210, 215, 230)), (SCREEN_W // 2 - 200, 318))
            br = (90, 140, 200) if join_focus == "room" else (45, 48, 62)
            pygame.draw.rect(screen, br, rect_room, border_radius=6)
            screen.blit(font_small.render(join_room, True, (245, 245, 250)), (SCREEN_W // 2 - 190, 358))
            screen.blit(font_small.render("In-game nickname (any name you like):", True, (210, 215, 230)), (SCREEN_W // 2 - 200, 398))
            bn = (90, 140, 200) if join_focus == "name" else (45, 48, 62)
            pygame.draw.rect(screen, bn, rect_name, border_radius=6)
            screen.blit(font_small.render(join_name or "…", True, (245, 245, 250)), (SCREEN_W // 2 - 190, 438))
            _draw_button(screen, btn_go, "Join game", font_small, btn_go.collidepoint(mx, my))

        if err_msg:
            screen.blit(font_small.render(err_msg, True, (255, 140, 140)), (40, SCREEN_H - 56))

        pygame.display.flip()
