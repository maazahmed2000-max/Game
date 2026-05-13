"""
Authoritative game server for online co-op.
Run from repo root:  uvicorn server.app:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import asyncio
import random
import secrets
import string
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kitchen import Order, RECIPE_BURGER, default_map, station_at
from player import Player


def _rid() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


class Room:
    def __init__(self, room_id: str, host_name: str) -> None:
        self.id = room_id
        self.cells = default_map()
        self.p1 = Player(2.0, 2.0)
        self.p2 = Player(5.0, 2.0)
        self.orders: List[Order] = []
        self.next_spawn = 2.5
        self.score = 0
        self.cd1 = 0.0
        self.cd2 = 0.0
        self.in1_dx = self.in1_dy = 0.0
        self.in2_dx = self.in2_dy = 0.0
        self.name1 = (host_name or "Chef")[:18]
        self.name2 = ""
        self.p2_joined = False


rooms: Dict[str, Room] = {}
rooms_lock = asyncio.Lock()
TICK = 1.0 / 30.0


def _try_interact(room: Room, player: Player, cd: float) -> float:
    if cd > 0 or not room.orders:
        return cd
    st = station_at(room.cells, *player.center_tile())
    if st is None:
        return cd
    for o in room.orders:
        if o.apply_station(st):
            if o.is_done():
                room.score += 10 + int(max(0, o.time_left))
                room.orders.remove(o)
            break
    return 0.22


def _tick_room(room: Room, dt: float) -> None:
    room.cd1 = max(0.0, room.cd1 - dt)
    room.cd2 = max(0.0, room.cd2 - dt)

    room.p1.update(room.cells, room.in1_dx, room.in1_dy, dt)
    if room.p2_joined:
        room.p2.update(room.cells, room.in2_dx, room.in2_dy, dt)

    room.next_spawn -= dt
    if room.next_spawn <= 0 and len(room.orders) < 3:
        room.orders.append(Order(RECIPE_BURGER, time_left=45.0 + random.random() * 15))
        room.next_spawn = 8.0 + random.random() * 6.0

    for o in room.orders:
        o.time_left -= dt
    for o in [x for x in room.orders if x.time_left <= 0]:
        room.orders.remove(o)
        room.score = max(0, room.score - 5)


def _order_hud(room: Room) -> str:
    if not room.orders:
        return "Waiting for orders…"
    o = room.orders[0]
    return f"{o.progress_text()}  |  time {o.time_left:.0f}s"


def _state_dict(room: Room) -> dict:
    return {
        "p1": {"c": room.p1.col, "r": room.p1.row},
        "p2": {"c": room.p2.col, "r": room.p2.row},
        "score": room.score,
        "order_hud": _order_hud(room),
        "p2_joined": room.p2_joined,
        "names": {"1": room.name1, "2": room.name2 or "…"},
    }


app = FastAPI(title="Kitchen Rush API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRoomBody(BaseModel):
    host_name: str = "Chef"


class JoinBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=18)


class InputBody(BaseModel):
    player: int = Field(..., ge=1, le=2)
    dx: float = 0.0
    dy: float = 0.0
    pulse_interact: bool = False


@app.post("/api/rooms")
async def create_room(body: CreateRoomBody) -> dict:
    rid = _rid()
    while rid in rooms:
        rid = _rid()
    async with rooms_lock:
        rooms[rid] = Room(rid, body.host_name.strip() or "Chef")
    return {"room_id": rid, "player": 1}


@app.post("/api/rooms/{room_id}/join")
async def join_room(room_id: str, body: JoinBody) -> dict:
    async with rooms_lock:
        room = rooms.get(room_id.upper())
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.p2_joined:
            raise HTTPException(status_code=409, detail="Room is full")
        room.p2_joined = True
        room.name2 = body.username.strip()[:18] or "Guest"
    return {"player": 2, "room_id": room_id.upper()}


@app.get("/api/rooms/{room_id}/state")
async def get_state(room_id: str) -> dict:
    async with rooms_lock:
        room = rooms.get(room_id.upper())
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        return _state_dict(room)


@app.post("/api/rooms/{room_id}/input")
async def post_input(room_id: str, body: InputBody) -> dict:
    async with rooms_lock:
        room = rooms.get(room_id.upper())
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if body.player == 1:
            room.in1_dx, room.in1_dy = body.dx, body.dy
            if body.pulse_interact:
                room.cd1 = _try_interact(room, room.p1, room.cd1)
        elif body.player == 2:
            if not room.p2_joined:
                raise HTTPException(status_code=400, detail="Player 2 not in room")
            room.in2_dx, room.in2_dy = body.dx, body.dy
            if body.pulse_interact:
                room.cd2 = _try_interact(room, room.p2, room.cd2)
    return {"ok": True}


async def _tick_loop() -> None:
    while True:
        await asyncio.sleep(TICK)
        async with rooms_lock:
            for room in list(rooms.values()):
                _tick_room(room, TICK)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_tick_loop())
