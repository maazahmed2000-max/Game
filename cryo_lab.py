"""Cryo level tester — sample flow through bond table and cryostat."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple

from constants import CRYO_ALIGN_HOLD_S, CRYO_COOL_S, CRYO_TEST_S, CRYO_WARM_S
from cryo_layout import get_cryo_layout
from lab import (
    INTERACT_RADIUS,
    Cell,
    in_vicinity,
    in_vicinity_of_station,
    layout_camera_anchor,
    random_spawn_booth,
    world_walkable,
)


class CryoStep(Enum):
    INCOMING = auto()
    BOND = auto()
    CRYO_LOAD = auto()
    CRYO_UNLOAD = auto()
    OUTGOING = auto()


CRYO_RECIPE: Tuple[CryoStep, ...] = (
    CryoStep.INCOMING,
    CryoStep.BOND,
    CryoStep.CRYO_LOAD,
    CryoStep.CRYO_UNLOAD,
    CryoStep.OUTGOING,
)


class CryostatPhase(Enum):
    EMPTY_WARM = auto()
    LOADED_WARM = auto()
    COOLING = auto()
    COLD = auto()
    ALIGNING = auto()
    ALIGNED = auto()
    TESTING = auto()
    TEST_PASSED = auto()
    WARMING = auto()
    WARM_LOADED = auto()


def cryo_step_label(step: CryoStep) -> str:
    return {
        CryoStep.INCOMING: "Incoming",
        CryoStep.BOND: "Hotplate bonder",
        CryoStep.CRYO_LOAD: "Cryostat (load)",
        CryoStep.CRYO_UNLOAD: "Cryostat (unload)",
        CryoStep.OUTGOING: "Outgoing",
    }[step]


def cryo_phase_label(phase: CryostatPhase) -> str:
    return {
        CryostatPhase.EMPTY_WARM: "Warm · empty",
        CryostatPhase.LOADED_WARM: "Warm · load sample",
        CryostatPhase.COOLING: "Cooling…",
        CryostatPhase.COLD: "Cold · align",
        CryostatPhase.ALIGNING: "Aligning…",
        CryostatPhase.ALIGNED: "Aligned · quick test",
        CryostatPhase.TESTING: "Testing…",
        CryostatPhase.TEST_PASSED: "Test OK · start warm",
        CryostatPhase.WARMING: "Warming…",
        CryostatPhase.WARM_LOADED: "Warm · remove sample",
    }[phase]


@dataclass(frozen=True)
class CryoStation:
    station_id: str
    col: float
    row: float
    radius: float = 1.4


def _anchor() -> Tuple[float, float]:
    return layout_camera_anchor()


def bond_table_station() -> CryoStation:
    lay = get_cryo_layout()
    return CryoStation("bond", lay.bond_c, lay.bond_r, lay.bond_radius)


def cryostat_station() -> CryoStation:
    lay = get_cryo_layout()
    return CryoStation("cryostat", lay.cryostat_c, lay.cryostat_r, lay.cryostat_radius)


def near_cryo_station(col: float, row: float, station: CryoStation) -> bool:
    return (col - station.col) ** 2 + (row - station.row) ** 2 <= station.radius**2


def cryo_default_map() -> List[List[Cell]]:
    """Cryo lab floor — uses cryo_layout.json, not the prober dev_layout."""
    from lab import build_floor_map

    return build_floor_map(get_cryo_layout())


def find_cryo_spawn(cells: List[List[Cell]]) -> Tuple[float, float]:
    ac, ar = _anchor()
    for radius in range(0, 12):
        for dc in range(-radius, radius + 1):
            for dr in range(-radius, radius + 1):
                if abs(dc) != radius and abs(dr) != radius and radius > 0:
                    continue
                wc, wr = ac + dc, ar + dr
                if world_walkable(cells, wc, wr):
                    return wc, wr
    return ac, ar


@dataclass
class CryoSample:
    """One die/sample lot through the cryo tester."""

    spawn_booth: Tuple[int, int]
    completed: List[CryoStep] = field(default_factory=list)
    label: str = "Sample"
    in_cryostat: bool = False

    def next_step(self) -> Optional[CryoStep]:
        if self.in_cryostat:
            return None
        idx = len(self.completed)
        if idx >= len(CRYO_RECIPE):
            return None
        return CRYO_RECIPE[idx]

    def advance(self, step: CryoStep) -> bool:
        expected = self.next_step()
        if expected is None or step != expected:
            return False
        self.completed.append(step)
        return True

    def is_done(self) -> bool:
        return len(self.completed) >= len(CRYO_RECIPE)


@dataclass
class Cryostat:
    phase: CryostatPhase = CryostatPhase.EMPTY_WARM
    timer: float = 0.0
    align_progress: float = 0.0
    loaded_sample_idx: Optional[int] = None

    def has_sample(self) -> bool:
        return self.loaded_sample_idx is not None

    def can_load(self) -> bool:
        return self.phase == CryostatPhase.EMPTY_WARM and not self.has_sample()

    def tick(self, dt: float, *, player_at_cryostat: bool) -> None:
        if self.phase == CryostatPhase.COOLING:
            self.timer += dt
            if self.timer >= CRYO_COOL_S:
                self.phase = CryostatPhase.COLD
                self.timer = 0.0
        elif self.phase == CryostatPhase.ALIGNING:
            if player_at_cryostat:
                self.align_progress += dt
                if self.align_progress >= CRYO_ALIGN_HOLD_S:
                    self.phase = CryostatPhase.ALIGNED
                    self.align_progress = 0.0
            else:
                self.align_progress = max(0.0, self.align_progress - dt * 0.5)
        elif self.phase == CryostatPhase.TESTING:
            self.timer += dt
            if self.timer >= CRYO_TEST_S:
                self.phase = CryostatPhase.TEST_PASSED
                self.timer = 0.0
        elif self.phase == CryostatPhase.WARMING:
            self.timer += dt
            if self.timer >= CRYO_WARM_S:
                self.phase = CryostatPhase.WARM_LOADED
                self.timer = 0.0

    def start_cooldown(self) -> bool:
        if self.phase != CryostatPhase.LOADED_WARM:
            return False
        self.phase = CryostatPhase.COOLING
        self.timer = 0.0
        return True

    def start_align(self) -> bool:
        if self.phase != CryostatPhase.COLD:
            return False
        self.phase = CryostatPhase.ALIGNING
        self.align_progress = 0.0
        return True

    def start_test(self) -> bool:
        if self.phase != CryostatPhase.ALIGNED:
            return False
        self.phase = CryostatPhase.TESTING
        self.timer = 0.0
        return True

    def start_warmup(self) -> bool:
        if self.phase != CryostatPhase.TEST_PASSED:
            return False
        self.phase = CryostatPhase.WARMING
        self.timer = 0.0
        return True

    def load_sample(self, sample_idx: int) -> bool:
        if not self.can_load():
            return False
        self.loaded_sample_idx = sample_idx
        self.phase = CryostatPhase.LOADED_WARM
        return True

    def unload_sample(self) -> bool:
        if self.phase != CryostatPhase.WARM_LOADED or self.loaded_sample_idx is None:
            return False
        self.loaded_sample_idx = None
        self.phase = CryostatPhase.EMPTY_WARM
        self.timer = 0.0
        self.align_progress = 0.0
        return True

    def phase_progress(self) -> float:
        if self.phase == CryostatPhase.COOLING:
            return min(1.0, self.timer / CRYO_COOL_S)
        if self.phase == CryostatPhase.ALIGNING:
            return min(1.0, self.align_progress / CRYO_ALIGN_HOLD_S)
        if self.phase == CryostatPhase.TESTING:
            return min(1.0, self.timer / CRYO_TEST_S)
        if self.phase == CryostatPhase.WARMING:
            return min(1.0, self.timer / CRYO_WARM_S)
        return 0.0


def cryo_interaction_hint(
    samples: List[CryoSample],
    cryostat: Cryostat,
    *,
    carrying_idx: Optional[int],
    col: float,
    row: float,
    cells: List[List[Cell]],
) -> Optional[str]:
    """Short HUD status for the next player action."""
    bond = bond_table_station()
    cryo = cryostat_station()

    if carrying_idx is not None and 0 <= carrying_idx < len(samples):
        s = samples[carrying_idx]
        step = s.next_step()
        if step == CryoStep.BOND and near_cryo_station(col, row, bond):
            return "Bond sample on hotplate (Space)"
        if step == CryoStep.CRYO_LOAD:
            if not cryostat.can_load():
                return "Cryostat not ready"
            if near_cryo_station(col, row, cryo):
                return "Load sample in warm cryostat (Space)"
            return "Carry sample to cryostat"
        if step == CryoStep.OUTGOING:
            if in_vicinity_of_station(cells, col, row, Cell.FINISHED_RACK):
                return "Place in outgoing rack (Space)"
            return "Carry sample to outgoing rack"
        if step is not None:
            return f"Next: {cryo_step_label(step)}"
        return None

    if cryostat.phase == CryostatPhase.LOADED_WARM and near_cryo_station(col, row, cryo):
        return "Start cooldown (Space)"
    if cryostat.phase == CryostatPhase.COLD and near_cryo_station(col, row, cryo):
        return "Stand here — hold Space to align"
    if cryostat.phase == CryostatPhase.ALIGNING and near_cryo_station(col, row, cryo):
        return "Aligning sample…"
    if cryostat.phase == CryostatPhase.ALIGNED and near_cryo_station(col, row, cryo):
        return "Start quick test (Space)"
    if cryostat.phase == CryostatPhase.TESTING and near_cryo_station(col, row, cryo):
        return "Running quick test…"
    if cryostat.phase == CryostatPhase.TEST_PASSED and near_cryo_station(col, row, cryo):
        return "Start warm-up (Space)"
    if cryostat.phase == CryostatPhase.WARM_LOADED and near_cryo_station(col, row, cryo):
        return "Remove sample from cryostat (Space)"

    for i, s in enumerate(samples):
        if s.next_step() == CryoStep.INCOMING and in_vicinity(col, row, s.spawn_booth):
            return "Pick up incoming sample (Space)"

    if cryostat.has_sample() and cryostat.phase in (
        CryostatPhase.COOLING,
        CryostatPhase.TESTING,
        CryostatPhase.WARMING,
    ):
        return cryo_phase_label(cryostat.phase)

    return None


def cryo_step_destination(
    samples: List[CryoSample],
    cryostat: Cryostat,
    sample: CryoSample,
    *,
    carrying: bool,
    cells: List[List[Cell]],
) -> Optional[Tuple[int, int]]:
    step = sample.next_step()
    if step is None and sample.in_cryostat:
        z = cryostat_station()
        if cryostat.phase in (
            CryostatPhase.LOADED_WARM,
            CryostatPhase.COLD,
            CryostatPhase.ALIGNING,
            CryostatPhase.ALIGNED,
            CryostatPhase.TESTING,
            CryostatPhase.TEST_PASSED,
            CryostatPhase.WARM_LOADED,
        ):
            return int(round(z.col)), int(round(z.row))
        return None
    if step == CryoStep.INCOMING and not carrying:
        return sample.spawn_booth
    if step == CryoStep.BOND:
        z = bond_table_station()
        return int(round(z.col)), int(round(z.row))
    if step == CryoStep.CRYO_LOAD and cryostat.can_load():
        z = cryostat_station()
        return int(round(z.col)), int(round(z.row))
    if step == CryoStep.OUTGOING:
        lay = get_cryo_layout()
        return lay.finished_c, lay.finished_r
    return None


def cryo_focus_sample(
    samples: List[CryoSample],
    cryostat: Cryostat,
    carrying_idx: Optional[int],
    col: float,
    row: float,
    cells: List[List[Cell]],
) -> Optional[CryoSample]:
    if carrying_idx is not None and 0 <= carrying_idx < len(samples):
        return samples[carrying_idx]
    bond = bond_table_station()
    cryo = cryostat_station()
    for s in samples:
        step = s.next_step()
        if step == CryoStep.INCOMING and in_vicinity(col, row, s.spawn_booth):
            return s
        if step == CryoStep.BOND and near_cryo_station(col, row, bond):
            return s
        if step == CryoStep.CRYO_LOAD and near_cryo_station(col, row, cryo):
            return s
    if cryostat.has_sample():
        idx = cryostat.loaded_sample_idx
        if idx is not None and 0 <= idx < len(samples):
            if cryostat.phase in (
                CryostatPhase.LOADED_WARM,
                CryostatPhase.COLD,
                CryostatPhase.ALIGNING,
                CryostatPhase.ALIGNED,
                CryostatPhase.TESTING,
                CryostatPhase.TEST_PASSED,
                CryostatPhase.WARM_LOADED,
            ):
                return samples[idx]
            if near_cryo_station(col, row, cryo):
                return samples[idx]
    return samples[0] if samples else None


def new_cryo_sample() -> CryoSample:
    n = random.randint(1, 99)
    return CryoSample(spawn_booth=random_spawn_booth(), label=f"Die {n}")
