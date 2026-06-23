"""Cryo level — station markers and progress overlays."""



from __future__ import annotations



from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Tuple



import pygame



from cryo_lab import (

    CryoSample,

    Cryostat,

    CryostatPhase,

    bond_table_station,

    cryo_phase_label,

    cryostat_station,

)

from cryo_layout import player_draws_in_front_of_bond, player_draws_in_front_of_cryostat

from iso_render import IsoView, draw_objective_arrow, draw_players_iso, draw_progress_at_world



if TYPE_CHECKING:

    from game_assets import GameAssets





def _draw_cryostat_overlays(

    surf: pygame.Surface,

    view: IsoView,

    cryostat: Cryostat,

    font: pygame.font.Font,

) -> None:

    cryo = cryostat_station()

    phase = cryo_phase_label(cryostat.phase)

    prog = cryostat.phase_progress()

    if cryostat.phase in (

        CryostatPhase.COOLING,

        CryostatPhase.ALIGNING,

        CryostatPhase.TESTING,

        CryostatPhase.WARMING,

    ):

        bar_color = (100, 180, 255)

        if cryostat.phase == CryostatPhase.TESTING:

            bar_color = (255, 200, 100)

        elif cryostat.phase == CryostatPhase.WARMING:

            bar_color = (255, 160, 100)

        draw_progress_at_world(

            surf,

            view,

            cryo.col,

            cryo.row,

            prog,

            bar_color,

            phase,

            font,

        )

    else:

        sx, sy = view.center(cryo.col, cryo.row)

        status = font.render(phase, True, (180, 220, 255))

        surf.blit(status, (int(sx - status.get_width() / 2), int(sy - view.hh * 3.6)))





def draw_cryo_equipment_depth_sorted(

    surf: pygame.Surface,

    view: IsoView,

    assets: "GameAssets",

    cryostat: Cryostat,

    font: pygame.font.Font,

    players: Sequence[Tuple[float, float, Tuple[int, int, int]]],

    *,

    carries: Optional[Sequence[bool]] = None,

    moving: Optional[Sequence[bool]] = None,

    facings: Optional[Sequence[bool]] = None,

    facing_mirrors: Optional[Sequence[bool]] = None,

    operators: Optional[Sequence[int]] = None,

) -> None:

    """Draw bench + cryostat vs operator with front/behind rules from cryo_layout.json."""

    from game_assets import BOND_BENCH_WIDTH_FACTOR, CRYOSTAT_WIDTH_FACTOR



    bond = bond_table_station()

    cryo = cryostat_station()

    bond_center = view.center(bond.col, bond.row)

    cryo_center = view.center(cryo.col, cryo.row)

    bench_w = view.hw * BOND_BENCH_WIDTH_FACTOR

    cryo_w = view.hw * CRYOSTAT_WIDTH_FACTOR



    def _draw_bench() -> None:

        assets.draw_bond_bench(surf, bond_center, bench_w)



    def _draw_cryo_unit() -> None:

        assets.draw_cryostat(surf, cryo_center, cryo_w)



    def _draw_players() -> None:

        draw_players_iso(

            surf,

            view,

            players,

            carries,

            assets=assets,

            moving=moving,

            facings=facings,

            facing_mirrors=facing_mirrors,

            operators=operators,

        )



    if not players:

        _draw_bench()

        _draw_cryo_unit()

        _draw_cryostat_overlays(surf, view, cryostat, font)

        return



    pcol, prow = players[0][0], players[0][1]

    _, player_foot_y = view.center(pcol, prow)

    player_foot_y += view.hh * 0.15

    bond_foot_y = assets.bond_bench_foot_y(bond_center, bench_w)

    cryo_foot_y = assets.cryostat_foot_y(cryo_center, cryo_w)



    before: List[Callable[[], None]] = []

    after: List[Callable[[], None]] = []



    if player_draws_in_front_of_bond(

        pcol, prow, player_foot_y=player_foot_y, bond_foot_y=bond_foot_y

    ):

        after.append(_draw_bench)

    else:

        before.append(_draw_bench)



    if player_draws_in_front_of_cryostat(

        pcol, prow, player_foot_y=player_foot_y, cryo_foot_y=cryo_foot_y

    ):

        after.append(_draw_cryo_unit)

    else:

        before.append(_draw_cryo_unit)



    for fn in before:

        fn()

    _draw_players()

    for fn in after:

        fn()

    _draw_cryostat_overlays(surf, view, cryostat, font)





def draw_cryo_world(

    surf: pygame.Surface,

    view: IsoView,

    cells: List,

    assets: "GameAssets",

    cryostat: Cryostat,

    samples: List[CryoSample],

    font: pygame.font.Font,

    *,

    objective_arrow: Optional[tuple[float, float, int, int, float]] = None,

    pending_tiles: Optional[List[tuple[int, int]]] = None,

    players: Optional[Sequence[Tuple[float, float, Tuple[int, int, int]]]] = None,

    carries: Optional[Sequence[bool]] = None,

    moving: Optional[Sequence[bool]] = None,

    facings: Optional[Sequence[bool]] = None,

    facing_mirrors: Optional[Sequence[bool]] = None,

    operators: Optional[Sequence[int]] = None,

) -> None:

    from iso_render import draw_pending_wafer



    assets.draw_background(surf)



    from lab import Cell



    for r in range(len(cells)):

        for c in range(len(cells[0])):

            if cells[r][c] in (Cell.RECEIVING, Cell.FINISHED_RACK):

                sx, sy = view.center(c, r)

                color = (230, 190, 70) if cells[r][c] == Cell.RECEIVING else (120, 200, 120)

                pygame.draw.circle(surf, color, (int(sx), int(sy)), 6, 2)



    for c, r in pending_tiles or []:

        draw_pending_wafer(surf, view, c, r, assets)



    if players is not None:

        draw_cryo_equipment_depth_sorted(

            surf,

            view,

            assets,

            cryostat,

            font,

            players,

            carries=carries,

            moving=moving,

            facings=facings,

            facing_mirrors=facing_mirrors,

            operators=operators,

        )

    else:

        from game_assets import BOND_BENCH_WIDTH_FACTOR, CRYOSTAT_WIDTH_FACTOR



        bond = bond_table_station()

        cryo = cryostat_station()

        assets.draw_bond_bench(

            surf, view.center(bond.col, bond.row), view.hw * BOND_BENCH_WIDTH_FACTOR

        )

        assets.draw_cryostat(

            surf, view.center(cryo.col, cryo.row), view.hw * CRYOSTAT_WIDTH_FACTOR

        )

        _draw_cryostat_overlays(surf, view, cryostat, font)



    if objective_arrow is not None:

        pcol, prow, tcol, trow, pulse_t = objective_arrow

        draw_objective_arrow(surf, view, pcol, prow, tcol, trow, pulse_t=pulse_t)

