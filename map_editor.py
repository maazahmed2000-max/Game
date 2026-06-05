"""Dev-only: paint floor tiles and drag handles for walls / station zones."""

from __future__ import annotations

import copy
import math
from typing import List, Optional, Set, Tuple

import pygame

from constants import COLS, DEBUG_MAP_EDITOR, ROWS
from dev_layout import (
    DevLayout,
    LatticeCoord,
    ZoneDef,
    apply_layout,
    apply_prober_anchor_drag,
    commit_layout,
    get_layout,
)
from display import logical_mouse_pos
from iso_render import IsoView, draw_zone_hitbox
from lab import (
    Cell,
    ProberSortOutcome,
    StationZone,
    _structural_blocked,
    prober_sort_in_near_zone,
    prober_sort_outcome,
)

Point = Tuple[float, float]
Handle = Tuple[str, float, float]
Tile = Tuple[int, int]  # world grid (col, row)

_APPROACH_DIRS: Tuple[Tuple[float, float, str], ...] = (
    (1.0, 0.0, "E"),
    (-1.0, 0.0, "W"),
    (0.0, 1.0, "S"),
    (0.0, -1.0, "N"),
    (0.7071, 0.7071, "SE"),
    (-0.7071, -0.7071, "NW"),
    (0.7071, -0.7071, "NE"),
    (-0.7071, 0.7071, "SW"),
)

_SORT_ZONE_FILL: dict[ProberSortOutcome, Tuple[int, int, int, int]] = {
    "front": (70, 210, 120, 52),
    "behind": (230, 75, 75, 58),
    "strip": (245, 195, 70, 72),
}

_SORT_ARROW_COLOR: dict[ProberSortOutcome, Tuple[int, int, int]] = {
    "front": (100, 255, 150),
    "behind": (255, 100, 100),
    "strip": (255, 220, 100),
}

_SORT_ARROW_LABEL: dict[ProberSortOutcome, str] = {
    "front": "ON TOP",
    "behind": "UNDER",
    "strip": "FLIP?",
}


class MapEditor:
    def __init__(self) -> None:
        self.active = False
        self.layout = get_layout()
        self.selected = "tiles"
        self._drag_id: Optional[str] = None
        self._drag_anchor: Tuple[float, float] = (0.0, 0.0)
        self._layout_start: Optional[DevLayout] = None
        self._paint_last: Optional[LatticeCoord] = None
        self._selections = [
            "tiles",
            "axes",
            "walls",
            "storage",
            "receiving",
            "labels",
            "anchor",
            "prober_front",
            "spade",
            "finished",
            "zone:mhu",
            "zone:rack_l",
            "zone:rack_r",
            "zone:chuck_l",
            "zone:chuck_r",
            "zone:load_l",
            "zone:load_r",
        ]

    def set_enabled(self, on: bool) -> None:
        self.active = on
        if on:
            self.layout = get_layout()
            self._paint_last = None
        else:
            self.end_drag(commit=True)
            self.persist()

    def persist(self) -> bool:
        """Write current editor layout to dev_layout.json."""
        apply_layout(self.layout)
        return commit_layout(self.layout)

    def end_drag(self, *, commit: bool = True) -> None:
        if self._drag_id and commit:
            self.persist()
        self._drag_id = None
        self._layout_start = None

    def toggle(self) -> bool:
        self.set_enabled(not self.active)
        return self.active

    def cycle_selection(self, step: int = 1) -> None:
        i = self._selections.index(self.selected) if self.selected in self._selections else 0
        self.selected = self._selections[(i + step) % len(self._selections)]
        self._paint_last = None

    def screen_to_grid(self, view: IsoView, sx: float, sy: float) -> Tuple[float, float]:
        hw, hh, ox, oy = view.hw, view.hh, view.ox, view.oy
        c = ((sx - ox) / hw + (sy - oy) / hh) * 0.5
        r = ((sy - oy) / hh - (sx - ox) / hw) * 0.5
        return c, r

    def _snap_lattice_at(self, view: IsoView, pos: Tuple[int, int]) -> LatticeCoord:
        gc, gr = self.screen_to_grid(view, *pos)
        return self.layout.snap_paint_lattice(gc, gr)

    def _paint_lattice(self, cell: LatticeCoord, *, block: bool) -> None:
        if self._paint_last == cell:
            return
        self._paint_last = cell
        self.layout.set_lattice_blocked(cell[0], cell[1], block)

    def _paint_at(self, view: IsoView, pos: Tuple[int, int], *, block: bool) -> bool:
        cell = self._snap_lattice_at(view, pos)
        self._paint_lattice(cell, block=block)
        return True

    def _label_handles(self, layout: DevLayout) -> List[Handle]:
        return [
            ("label_storage", *layout.label_storage()),
            ("label_rack_l", *layout.label_rack_l()),
            ("label_rack_r", *layout.label_rack_r()),
            ("label_prober", *layout.label_prober()),
            ("label_mhu", *layout.label_mhu()),
            ("label_chuck_l", *layout.label_chuck_l()),
            ("label_chuck_r", *layout.label_chuck_r()),
        ]

    def _handles_visible(self, layout: DevLayout) -> List[Handle]:
        """Selection handles; label handles are always shown while editing."""
        primary = self._handles(layout)
        if self.selected == "labels":
            return primary
        return primary + self._label_handles(layout)

    def _handles(self, layout: DevLayout) -> List[Handle]:
        if self.selected == "tiles":
            return []

        if self.selected == "axes":
            ox, oy = layout.tile_origin()
            xtip = layout.axis_x_tip()
            ytip = layout.axis_y_tip()
            return [
                ("axis_o", ox, oy),
                ("axis_x", xtip[0], xtip[1]),
                ("axis_y", ytip[0], ytip[1]),
            ]

        if self.selected == "labels":
            return self._label_handles(layout)

        h: List[Handle] = []
        for i, (c, r) in enumerate(layout.play_bounds_corners):
            h.append((f"play_c:{i}", c, r))

        if self.selected == "receiving":
            booths = layout.receiving_booths
            for i, (c, r) in enumerate(booths):
                h.append((f"receiving:{i}", c + 0.5, r + 0.5))
            if booths:
                cx = sum(c for c, _ in booths) / len(booths)
                cr = sum(r for _, r in booths) / len(booths)
                h.append(("receiving_all", cx, cr))

        if self.selected == "anchor":
            h.append(("prober_c", layout.prober_cx, layout.prober_cy))

        if self.selected == "prober_front":
            ox, oy = layout.prober_front_origin()
            h.append(("prober_front_o", ox, oy))
            tip = layout.prober_front_tip()
            h.append(("prober_front", tip[0], tip[1]))
            pc, pr = layout.prober_cx, layout.prober_cy
            nr = layout.prober_sort_near_radius
            h.append(("prober_sort_r", pc + nr, pr))

        if self.selected == "spade":
            play_tl = layout.play_bounds_corners[0]
            h.append(("spade_tl", layout.spade_c0 + 0.5, play_tl[1]))
            h.append(("spade_br", COLS - 1.5, layout.spade_r1 + 0.5))
        h.append(("finished", layout.finished_c, layout.finished_r))

        for zid, zd in layout.zones.items():
            if self.selected == f"zone:{zid}":
                h.append((f"zone_pos:{zid}", layout.prober_cx + zd.dx, layout.prober_cy + zd.dy))
                h.append(
                    (f"zone_rad:{zid}", layout.prober_cx + zd.dx + zd.radius * 0.7, layout.prober_cy + zd.dy)
                )
        return h

    def _label_screen_xy(
        self, view: IsoView, col: float, row: float, *, lift: float
    ) -> Point:
        cx, cy = view.center(col, row)
        cy -= view.hh * lift
        return cx, cy

    def _pick_label_handle(self, view: IsoView, mx: int, my: int) -> Optional[str]:
        """Screen-space pick on visible label anchors (easier than grid handles)."""
        lay = self.layout
        candidates: Tuple[Tuple[str, float, float, float], ...] = (
            ("label_storage", *lay.label_storage(), 3.2),
            ("label_rack_l", *lay.label_rack_l(), 4.5),
            ("label_rack_r", *lay.label_rack_r(), 4.5),
            ("label_prober", *lay.label_prober(), 2.2),
            ("label_mhu", *lay.label_mhu(), 2.2),
            ("label_chuck_l", *lay.label_chuck_l(), 2.2),
            ("label_chuck_r", *lay.label_chuck_r(), 2.2),
        )
        best: Optional[str] = None
        best_d = 999.0
        for hid, col, row, lift in candidates:
            sx, sy = self._label_screen_xy(view, col, row, lift=lift)
            d = math.hypot(mx - sx, my - sy)
            if d < 64.0 and d < best_d:
                best_d = d
                best = hid
        return best

    @staticmethod
    def _mouse_xy(event: pygame.event.Event) -> Tuple[int, int]:
        if hasattr(event, "pos"):
            return logical_mouse_pos(event.pos)
        return logical_mouse_pos(pygame.mouse.get_pos())

    def _pick_handle(self, view: IsoView, mx: int, my: int) -> Optional[str]:
        label = self._pick_label_handle(view, mx, my)
        if label is not None:
            return label
        best: Optional[str] = None
        best_d = 999.0
        for hid, col, row in self._handles_visible(self.layout):
            if hid.startswith("label_"):
                continue
            sx, sy = view.center(col, row)
            d = math.hypot(mx - sx, my - sy)
            if d < 28.0 and d < best_d:
                best_d = d
                best = hid
        return best

    @property
    def is_dragging(self) -> bool:
        return self._drag_id is not None

    def continue_drag(self, view: IsoView, pos: Tuple[int, int]) -> None:
        if self._drag_id and self._layout_start:
            self._apply_drag(view, pos)
            apply_layout(self.layout)

    def _handle_pointer(self, event: pygame.event.Event, view: IsoView) -> bool:
        pos = self._mouse_xy(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hid = self._pick_handle(view, *pos)
            if hid:
                self._drag_id = hid
                gc, gr = self.screen_to_grid(view, *pos)
                self._drag_anchor = (gc, gr)
                self._layout_start = copy.deepcopy(self.layout)
                return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_drag = self._drag_id is not None
            self.end_drag(commit=was_drag)
            return was_drag

        if event.type == pygame.MOUSEMOTION and self._drag_id and self._layout_start:
            self._apply_drag(view, pos)
            apply_layout(self.layout)
            return True

        return False

    def _handle_selected(self, hid: str) -> bool:
        if self.selected == "axes" and hid.startswith("axis_"):
            return True
        if hid.startswith("play_c:"):
            return True
        if self.selected == "receiving" and (hid == "receiving_all" or hid.startswith("receiving:")):
            return True
        if hid.startswith("label_"):
            return True
        if self.selected == "anchor" and hid == "prober_c":
            return True
        if self.selected == "prober_front" and hid in ("prober_front_o", "prober_front", "prober_sort_r"):
            return True
        if self.selected == "spade" and hid.startswith("spade_"):
            return True
        if self.selected == "finished" and hid == "finished":
            return True
        if self.selected.startswith("zone:"):
            zid = self.selected[5:]
            return hid.endswith(f":{zid}")
        return False

    def handle_event(self, event: pygame.event.Event, view: IsoView, *, enabled: bool) -> bool:
        if not DEBUG_MAP_EDITOR or not enabled:
            return False
        self.active = True

        if self._handle_pointer(event, view):
            return True

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self.cycle_selection(-1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1)
                return True
            if event.key == pygame.K_s:
                self.persist()
                return True
            if event.key == pygame.K_c and self.selected == "tiles":
                self.layout.blocked_lattice = []
                self.persist()
                return True
            if event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
                if self.selected.startswith("zone:"):
                    zid = self.selected[5:]
                    if zid in self.layout.zones:
                        z = self.layout.zones[zid]
                        delta = -0.05 if event.key == pygame.K_LEFTBRACKET else 0.05
                        self.layout.zones[zid] = type(z)(z.dx, z.dy, max(0.4, z.radius + delta), z.step)
                        self.persist()
                return True

        if self.selected == "receiving":
            pos = self._mouse_xy(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                tile = self._receiving_tile_at(view, pos)
                if self._toggle_receiving_booth(tile, add=event.button == 1):
                    self.persist()
                    return True
            return False

        if self.selected == "tiles":
            pos = self._mouse_xy(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                self._paint_last = None
                block = event.button == 1
                if self._paint_at(view, pos, block=block):
                    apply_layout(self.layout)
                    return True
            if event.type == pygame.MOUSEMOTION:
                buttons = pygame.mouse.get_pressed()
                if buttons[0] or buttons[2]:
                    block = bool(buttons[0])
                    if self._paint_at(view, pos, block=block):
                        apply_layout(self.layout)
                        return True
            if event.type == pygame.MOUSEBUTTONUP:
                self._paint_last = None
                self.persist()
            return False

        return False

    def _apply_drag(self, view: IsoView, pos: Tuple[int, int]) -> None:
        hid = self._drag_id
        start = self._layout_start
        if not hid or not start:
            return
        gc, gr = self.screen_to_grid(view, *pos)
        ac, ar = self._drag_anchor
        dc, dr = gc - ac, gr - ar
        lay = self.layout

        if hid.startswith("play_c:"):
            idx = int(hid.split(":")[1])
            corners = list(lay.play_bounds_corners)
            sc, sr = start.play_bounds_corners[idx]
            corners[idx] = (sc + dc, sr + dr)
            lay.play_bounds_corners = corners
        elif hid.startswith("storage_c:"):
            idx = int(hid.split(":")[1])
            corners = list(lay.storage_corners)
            sc, sr = start.storage_corners[idx]
            corners[idx] = (sc + dc, sr + dr)
            lay.storage_corners = corners

        elif hid == "label_storage":
            sc, sr = start.label_storage()
            lay.label_storage_c = sc + dc
            lay.label_storage_r = sr + dr
        elif hid == "label_rack_l":
            lc, lr = start.label_rack_l()
            lay.label_rack_l_c = lc + dc
            lay.label_rack_l_r = lr + dr
        elif hid == "label_rack_r":
            lc, lr = start.label_rack_r()
            lay.label_rack_r_c = lc + dc
            lay.label_rack_r_r = lr + dr
        elif hid == "label_prober":
            pc, pr = start.label_prober()
            lay.label_prober_c = pc + dc
            lay.label_prober_r = pr + dr
        elif hid == "label_mhu":
            mc, mr = start.label_mhu()
            lay.label_mhu_c = mc + dc
            lay.label_mhu_r = mr + dr
        elif hid == "label_chuck_l":
            lc, lr = start.label_chuck_l()
            lay.label_chuck_l_c = lc + dc
            lay.label_chuck_l_r = lr + dr
        elif hid == "label_chuck_r":
            lc, lr = start.label_chuck_r()
            lay.label_chuck_r_c = lc + dc
            lay.label_chuck_r_r = lr + dr

        elif hid == "receiving_all":
            ic, ir = int(round(dc)), int(round(dr))
            moved: List[Tile] = []
            for c, r in start.receiving_booths:
                nc = max(0, min(COLS - 1, c + ic))
                nr = max(0, min(ROWS - 1, r + ir))
                key = (nc, nr)
                if key not in moved:
                    moved.append(key)
            lay.receiving_booths = moved

        elif hid.startswith("receiving:"):
            idx = int(hid.split(":", 1)[1])
            if 0 <= idx < len(start.receiving_booths):
                c0, r0 = start.receiving_booths[idx]
                nc = max(0, min(COLS - 1, c0 + int(round(dc))))
                nr = max(0, min(ROWS - 1, r0 + int(round(dr))))
                booths = list(start.receiving_booths)
                booths[idx] = (nc, nr)
                deduped: List[Tile] = []
                for t in booths:
                    if t not in deduped:
                        deduped.append(t)
                lay.receiving_booths = deduped

        elif hid == "prober_c":
            apply_prober_anchor_drag(lay, start, dc, dr)

        elif hid == "prober_front_o":
            lay.prober_front_origin_c = start.prober_front_origin_c + dc
            lay.prober_front_origin_r = start.prober_front_origin_r + dr

        elif hid == "prober_front":
            ox, oy = lay.prober_front_origin_c, lay.prober_front_origin_r
            vx, vy = gc - ox, gr - oy
            if math.hypot(vx, vy) >= 0.35:
                lay.prober_front_dx = vx
                lay.prober_front_dy = vy

        elif hid == "prober_sort_r":
            dist = math.hypot(gc - lay.prober_cx, gr - lay.prober_cy)
            lay.prober_sort_near_radius = max(2.5, min(14.0, dist))

        elif hid == "axis_o":
            lay.tile_origin_c = start.tile_origin_c + dc
            lay.tile_origin_r = start.tile_origin_r + dr
        elif hid == "axis_x":
            ox, oy = start.tile_origin_c, start.tile_origin_r
            vx, vy = gc - ox, gr - oy
            if math.hypot(vx, vy) >= 0.2:
                lay.tile_axis_x = (vx, vy)
        elif hid == "axis_y":
            ox, oy = start.tile_origin_c, start.tile_origin_r
            vx, vy = gc - ox, gr - oy
            if math.hypot(vx, vy) >= 0.2:
                lay.tile_axis_y = (vx, vy)

        elif hid == "spade_tl":
            lay.spade_c0 = max(0, min(COLS - 1, start.spade_c0 + int(round(dc))))
        elif hid == "spade_br":
            lay.spade_r1 = max(0, min(ROWS - 1, start.spade_r1 + int(round(dr))))

        elif hid == "finished":
            lay.finished_c = max(0, min(COLS - 1, start.finished_c + int(round(dc))))
            lay.finished_r = max(0, min(ROWS - 1, start.finished_r + int(round(dr))))

        elif hid.startswith("zone_pos:"):
            zid = hid.split(":", 1)[1]
            z = start.zones[zid]
            # Offset from prober at drag start so the handle stays under the cursor.
            lay.zones[zid] = ZoneDef(
                z.dx + dc,
                z.dy + dr,
                z.radius,
                z.step,
            )
        elif hid.startswith("zone_rad:"):
            zid = hid.split(":", 1)[1]
            z = start.zones[zid]
            lay.zones[zid] = type(z)(z.dx, z.dy, max(0.4, z.radius + math.hypot(dc, dr) * 0.12), z.step)

    def _draw_arrow(
        self,
        surf: pygame.Surface,
        view: IsoView,
        font: pygame.font.Font,
        p0: Point,
        p1: Point,
        color: Tuple[int, int, int],
        label: str,
    ) -> None:
        a = view.center(p0[0], p0[1])
        b = view.center(p1[0], p1[1])
        ax, ay = int(a[0]), int(a[1])
        bx, by = int(b[0]), int(b[1])
        pygame.draw.line(surf, color, (ax, ay), (bx, by), 3)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length < 4:
            return
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        tip = 14.0
        base = 7.0
        head = [
            (bx, by),
            (bx - ux * tip + px * base, by - uy * tip + py * base),
            (bx - ux * tip - px * base, by - uy * tip - py * base),
        ]
        pygame.draw.polygon(surf, color, head)
        mx, my = (ax + bx) // 2, (ay + by) // 2
        t = font.render(label, True, color)
        surf.blit(t, (mx + 6, my - 10))

    def _draw_sort_zone_cell(
        self,
        layer: pygame.Surface,
        view: IsoView,
        col: float,
        row: float,
        fill: Tuple[int, int, int, int],
    ) -> None:
        pts = [(int(p[0]), int(p[1])) for p in view.corners_at(col, row)]
        if len(pts) >= 3:
            pygame.draw.polygon(layer, fill, pts)

    def _draw_prober_sort_zones(
        self, surf: pygame.Surface, view: IsoView, lay: DevLayout
    ) -> None:
        pc, pr = lay.prober_cx, lay.prober_cy
        near = lay.prober_sort_near_radius
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ir = int(math.ceil(near)) + 1
        for di in range(-ir, ir + 1):
            for dj in range(-ir, ir + 1):
                if di * di + dj * dj > near * near:
                    continue
                c, r = pc + di, pr + dj
                ic, irow = int(round(c)), int(round(r))
                if not (0 <= ic < COLS and 0 <= irow < ROWS) or _structural_blocked(ic, irow):
                    continue
                outcome = prober_sort_outcome(c, r)
                fill = _SORT_ZONE_FILL.get(outcome)
                if fill:
                    if not prober_sort_in_near_zone(c, r):
                        fill = (fill[0], fill[1], fill[2], max(20, fill[3] // 2))
                    self._draw_sort_zone_cell(layer, view, c, r, fill)
        surf.blit(layer, (0, 0))

    def _draw_prober_near_ring(self, surf: pygame.Surface, view: IsoView, lay: DevLayout) -> None:
        pc, pr = lay.prober_cx, lay.prober_cy
        near = lay.prober_sort_near_radius
        ring: List[Tuple[int, int]] = []
        for i in range(56):
            ang = (2.0 * math.pi * i) / 56.0
            c = pc + math.cos(ang) * near
            r = pr + math.sin(ang) * near
            sx, sy = view.center(c, r)
            ring.append((int(sx), int(sy)))
        if len(ring) >= 3:
            pygame.draw.lines(surf, (255, 220, 100), True, ring, 2)

    def _draw_approach_arrow(
        self,
        surf: pygame.Surface,
        view: IsoView,
        font: pygame.font.Font,
        p0: Point,
        p1: Point,
        outcome: ProberSortOutcome,
        dir_label: str,
    ) -> None:
        color = _SORT_ARROW_COLOR.get(outcome, (200, 200, 200))
        ax, ay = int(p0[0]), int(p0[1])
        bx, by = int(p1[0]), int(p1[1])
        pygame.draw.line(surf, color, (ax, ay), (bx, by), 2)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length < 6:
            return
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        tip, base = 11.0, 5.0
        head = [
            (bx, by),
            (bx - ux * tip + px * base, by - uy * tip + py * base),
            (bx - ux * tip - px * base, by - uy * tip - py * base),
        ]
        pygame.draw.polygon(surf, color, head)
        tag = _SORT_ARROW_LABEL.get(outcome, "")
        t = font.render(f"{dir_label} {tag}", True, color)
        surf.blit(t, (bx + 4, by - 14))

    def _draw_prober_approach_arrows(
        self, surf: pygame.Surface, view: IsoView, font: pygame.font.Font, lay: DevLayout
    ) -> None:
        pc, pr = lay.prober_cx, lay.prober_cy
        near = lay.prober_sort_near_radius
        for ux, uy, label in _APPROACH_DIRS:
            sample_c = pc + ux * near * 0.88
            sample_r = pr + uy * near * 0.88
            outcome = prober_sort_outcome(sample_c, sample_r)
            start_c = pc + ux * (near + 2.4)
            start_r = pr + uy * (near + 2.4)
            self._draw_approach_arrow(
                surf,
                view,
                font,
                view.center(start_c, start_r),
                view.center(sample_c, sample_r),
                outcome,
                label,
            )

    def _draw_prober_front(self, surf: pygame.Surface, view: IsoView, font: pygame.font.Font, lay: DevLayout) -> None:
        self._draw_prober_sort_zones(surf, view, lay)
        self._draw_prober_near_ring(surf, view, lay)
        self._draw_prober_approach_arrows(surf, view, font, lay)

        origin = lay.prober_front_origin()
        tip = lay.prober_front_tip()
        self._draw_arrow(surf, view, font, origin, tip, (90, 255, 150), "FRONT")
        ax, ay = view.center(lay.prober_cx, lay.prober_cy)
        pygame.draw.circle(surf, (160, 170, 200), (int(ax), int(ay)), 6, 2)
        ox, oy = view.center(origin[0], origin[1])
        pygame.draw.circle(surf, (255, 255, 180), (int(ox), int(oy)), 8)
        pygame.draw.circle(surf, (40, 40, 50), (int(ox), int(oy)), 8, 2)
        fx, fy = lay.prober_front_dir()
        perp = (-fy, fx)
        span = view.hw * 5.0
        p0 = (int(ox - perp[0] * span), int(oy - perp[1] * span * 0.5))
        p1 = (int(ox + perp[0] * span), int(oy + perp[1] * span * 0.5))
        pygame.draw.line(surf, (90, 255, 150), p0, p1, 1)

    def _receiving_tile_at(self, view: IsoView, pos: Tuple[int, int]) -> Tile:
        gc, gr = self.screen_to_grid(view, *pos)
        return max(0, min(COLS - 1, int(round(gc)))), max(0, min(ROWS - 1, int(round(gr))))

    def _toggle_receiving_booth(self, tile: Tile, *, add: bool) -> bool:
        booths = self.layout.receiving_booths
        if add:
            if tile in booths or _structural_blocked(tile[0], tile[1]):
                return False
            booths.append(tile)
            return True
        if tile not in booths:
            return False
        self.layout.receiving_booths = [t for t in booths if t != tile]
        return True

    def _draw_receiving_booths(self, surf: pygame.Surface, view: IsoView, lay: DevLayout) -> None:
        hover = self._receiving_tile_at(view, logical_mouse_pos(pygame.mouse.get_pos()))
        booth_set = set(lay.receiving_booths)
        for c, r in lay.receiving_booths:
            pts = [(int(p[0]), int(p[1])) for p in view.corners_floor(c, r)]
            if len(pts) >= 3:
                fill = (120, 255, 200) if (c, r) == hover else (80, 220, 170)
                pygame.draw.polygon(surf, fill, pts)
                pygame.draw.polygon(surf, (200, 255, 230), pts, 2)
        if hover not in booth_set and not _structural_blocked(hover[0], hover[1]):
            pts = [(int(p[0]), int(p[1])) for p in view.corners_floor(hover[0], hover[1])]
            if len(pts) >= 3:
                pygame.draw.polygon(surf, (120, 255, 200), pts, 2)

    def _draw_tile_axes(self, surf: pygame.Surface, view: IsoView, font: pygame.font.Font, lay: DevLayout) -> None:
        origin = lay.tile_origin()
        self._draw_arrow(surf, view, font, origin, lay.axis_x_tip(), (80, 220, 255), "X")
        self._draw_arrow(surf, view, font, origin, lay.axis_y_tip(), (255, 120, 200), "Y")
        ox, oy = origin
        sx, sy = view.center(ox, oy)
        pygame.draw.circle(surf, (255, 255, 180), (int(sx), int(sy)), 8)
        pygame.draw.circle(surf, (40, 40, 50), (int(sx), int(sy)), 8, 2)

    def _draw_lattice_cell(
        self,
        surf: pygame.Surface,
        view: IsoView,
        i: int,
        j: int,
        lay: DevLayout,
        *,
        fill: Tuple[int, int, int, int],
        outline: Tuple[int, int, int],
    ) -> None:
        corners = lay.lattice_corners(i, j)
        pts = [(int(view.center(c, r)[0]), int(view.center(c, r)[1])) for c, r in corners]
        if len(pts) >= 3:
            pygame.draw.polygon(surf, fill, pts)
            pygame.draw.polygon(surf, outline, pts, 2)

    def _draw_walkable_lattice(self, surf: pygame.Surface, view: IsoView, lay: DevLayout) -> None:
        """Draw every skew tile — open (walkable) and blocked — matching in-game hitboxes."""
        hover: Optional[LatticeCoord] = None
        if self.selected == "tiles":
            hover = self._snap_lattice_at(view, logical_mouse_pos(pygame.mouse.get_pos()))
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        for i in range(-32, 33):
            for j in range(-32, 33):
                wc, wr = lay.cell_center(i, j)
                ic, ir = int(round(wc)), int(round(wr))
                if not (0 <= ic < COLS and 0 <= ir < ROWS):
                    continue
                if _structural_blocked(ic, ir):
                    continue
                is_open = lay.is_cell_walkable(i, j)
                is_hover = hover == (i, j)
                if is_open:
                    fill = (120, 220, 255, 72) if is_hover else (70, 130, 210, 48)
                    outline = (180, 240, 255) if is_hover else (120, 180, 255)
                else:
                    fill = (255, 160, 100, 80) if is_hover else (255, 120, 80, 58)
                    outline = (255, 220, 160) if is_hover else (255, 180, 100)
                self._draw_lattice_cell(layer, view, i, j, lay, fill=fill, outline=outline)
        surf.blit(layer, (0, 0))

    def draw(self, surf: pygame.Surface, view: IsoView, font: pygame.font.Font, *, enabled: bool) -> None:
        if not DEBUG_MAP_EDITOR or not enabled:
            return
        lay = self.layout

        def quad_outline(corners: List[Tuple[float, float]], color: Tuple[int, int, int]) -> None:
            pts = [view.center(c, r) for c, r in corners]
            pygame.draw.lines(surf, color, True, [(int(p[0]), int(p[1])) for p in pts], 2)

        if self.selected in ("tiles", "axes"):
            self._draw_walkable_lattice(surf, view, lay)
        if self.selected == "prober_front":
            self._draw_prober_front(surf, view, font, lay)

        quad_outline(lay.play_bounds_corners, (180, 100, 255))

        if self.selected not in ("tiles", "axes", "labels"):
            if self.selected == "receiving":
                self._draw_receiving_booths(surf, view, lay)
            self._draw_walkable_lattice(surf, view, lay)

        zone_colors = {
            "PROBER_WAIT": (120, 180, 255),
            "TEST_BENCH": (100, 200, 170),
            "TEST_CHAMBER": (255, 160, 90),
            "PROBER_LOAD": (180, 190, 210),
        }
        if self.selected.startswith("zone:"):
            for zid, zd in lay.zones.items():
                zc = lay.prober_cx + zd.dx
                zr = lay.prober_cy + zd.dy
                step = Cell[zd.step] if zd.step in Cell.__members__ else Cell.PROBER_WAIT
                color = zone_colors.get(zd.step, (200, 200, 200))
                draw_zone_hitbox(
                    surf,
                    view,
                    StationZone(zid, zc, zr, step, zd.radius),
                    color,
                    active=self.selected == f"zone:{zid}",
                    show_radius=True,
                )

        label_lifts = {
            "label_storage": 3.2,
            "label_rack_l": 4.5,
            "label_rack_r": 4.5,
            "label_prober": 2.2,
            "label_mhu": 2.2,
            "label_chuck_l": 2.2,
            "label_chuck_r": 2.2,
        }
        for hid, col, row in self._handles_visible(lay):
            if hid.startswith("label_"):
                lift = label_lifts.get(hid, 3.0)
                sx, sy = self._label_screen_xy(view, col, row, lift=lift)
                color = (120, 255, 220) if self._drag_id == hid else (80, 220, 200)
                radius = 10
            elif hid.startswith("play_c:"):
                sx, sy = view.center(col, row)
                color = (255, 220, 120) if self._drag_id == hid else (200, 140, 255)
                radius = 9
            else:
                sx, sy = view.center(col, row)
                color = (255, 255, 120) if self._handle_selected(hid) else (255, 255, 255)
                radius = 7
            pygame.draw.circle(surf, color, (int(sx), int(sy)), radius)
            pygame.draw.circle(surf, (20, 20, 30), (int(sx), int(sy)), radius, 2)

        self._draw_tile_axes(surf, view, font, lay)

        n_blocked = len(lay.blocked_lattice)
        y = surf.get_height() - 112
        lines = [
            "MAP EDITOR — Editor toggle / M | Tab mode | auto-saves to dev_layout.json",
            f"Mode: {self.selected}  |  painted blocked tiles: {n_blocked}",
        ]
        if self.selected == "axes":
            lines.append("X/Y arrows set walkable tile shape — blue=walk, orange=block | Tab to paint")
        elif self.selected == "tiles":
            lines.append("LMB block / RMB open — parallelograms rebuild the walk grid (not overlay) | C clear")
        elif self.selected == "receiving":
            n_recv = len(lay.receiving_booths)
            lines.append(
                f"Incoming wafer booths: {n_recv}  |  LMB add tile  RMB remove  |  drag handles or center to move"
            )
        elif self.selected == "anchor":
            lines.append("Drag center — moves prober + floor together (zone offsets unchanged)")
        elif self.selected == "prober_front":
            lines.append(
                "Green=ON TOP  Red=UNDER  Amber=FLIP?  |  drag origin, FRONT, yellow ring radius"
            )
            lines.append(
                "Outside yellow ring: plane only — inside ring: FLIP? uses foot height"
            )
        elif self.selected == "labels":
            lines.append(
                "Drag UI labels (storage queue, racks, prober bar, MHU) — preview stays visible"
            )
        else:
            lines.append("Drag purple corner handles to resize play area  |  [ ] zone radius when a zone is selected")
        sw = surf.get_width()
        for line in lines:
            t = font.render(line, True, (255, 220, 140))
            surf.blit(t, (max(0, sw // 2 - t.get_width() // 2), y))
            y += 18
