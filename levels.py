"""Playable levels — room-temperature prober floor and cryo tester."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class LevelInfo:
    id: int
    title: str
    subtitle: str


LEVELS: Tuple[LevelInfo, ...] = (
    LevelInfo(1, "Room temperature", "Prober test floor"),
    LevelInfo(2, "Cryo", "Hotplate bonder + cryostat cycle"),
)

LEVEL_COUNT = len(LEVELS)


def level_by_id(level_id: int) -> LevelInfo | None:
    for level in LEVELS:
        if level.id == level_id:
            return level
    return None
