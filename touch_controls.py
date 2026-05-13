"""Dual on-screen sticks for touch / mobile (pygbag-friendly)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import pygame


Vec2 = Tuple[float, float]


@dataclass
class StickZone:
    center_x: float
    center_y: float
    radius: float
    dead: float = 0.12

    def vec_from_point(self, px: float, py: float) -> Vec2:
        dx = (px - self.center_x) / self.radius
        dy = (py - self.center_y) / self.radius
        mag = math.hypot(dx, dy)
        if mag < self.dead:
            return 0.0, 0.0
        if mag > 1.0:
            dx /= mag
            dy /= mag
        else:
            scale = (mag - self.dead) / (1.0 - self.dead)
            dx *= scale / max(mag, 1e-6)
            dy *= scale / max(mag, 1e-6)
        return dx, dy


@dataclass
class DualSticks:
    """Left stick → player 0, right stick → player 1."""

    screen_w: int
    screen_h: int
    margin: float = 24.0
    radius: float = 72.0
    left: StickZone = field(init=False)
    right: StickZone = field(init=False)
    p1_interact: pygame.Rect = field(init=False)
    p2_interact: pygame.Rect = field(init=False)
    _touch: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    _mouse_left: bool = False
    _interact_next: List[bool] = field(default_factory=lambda: [False, False])

    def __post_init__(self) -> None:
        r = self.radius
        m = self.margin
        self.left = StickZone(m + r, self.screen_h - m - r, r)
        self.right = StickZone(self.screen_w - m - r, self.screen_h - m - r, r)
        bw, bh = 76, 44
        self.p1_interact = pygame.Rect(int(m), int(self.screen_h - m - r * 2 - bh - 8), bw, bh)
        self.p2_interact = pygame.Rect(int(self.screen_w - m - bw), int(self.screen_h - m - r * 2 - bh - 8), bw, bh)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.FINGERDOWN:
            x = event.x * self.screen_w
            y = event.y * self.screen_h
            self._touch[event.finger_id] = (x, y)
            self._try_interact_tap(x, y)
        elif event.type == pygame.FINGERMOTION:
            if event.finger_id in self._touch:
                self._touch[event.finger_id] = (event.x * self.screen_w, event.y * self.screen_h)
        elif event.type == pygame.FINGERUP:
            self._touch.pop(event.finger_id, None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_left = True
            self._touch[-1] = (float(event.pos[0]), float(event.pos[1]))
            self._try_interact_tap(float(event.pos[0]), float(event.pos[1]))
        elif event.type == pygame.MOUSEMOTION and self._mouse_left:
            self._touch[-1] = (float(event.pos[0]), float(event.pos[1]))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_left = False
            self._touch.pop(-1, None)

    def _try_interact_tap(self, x: float, y: float) -> None:
        if self.p1_interact.collidepoint(x, y):
            self._interact_next[0] = True
        if self.p2_interact.collidepoint(x, y):
            self._interact_next[1] = True

    def pop_interact(self) -> Tuple[bool, bool]:
        a, b = self._interact_next[0], self._interact_next[1]
        self._interact_next[0] = False
        self._interact_next[1] = False
        return a, b

    def vectors(self) -> Tuple[Vec2, Vec2]:
        left_pts: List[Tuple[float, float]] = []
        right_pts: List[Tuple[float, float]] = []
        reach = self.radius * 1.25
        for px, py in self._touch.values():
            dl = math.hypot(px - self.left.center_x, py - self.left.center_y)
            dr = math.hypot(px - self.right.center_x, py - self.right.center_y)
            if dl <= reach and dl <= dr:
                left_pts.append((px, py))
            elif dr <= reach:
                right_pts.append((px, py))

        def avg(zone: StickZone, pts: List[Tuple[float, float]]) -> Vec2:
            if not pts:
                return 0.0, 0.0
            sx = sy = 0.0
            for px, py in pts:
                vx, vy = zone.vec_from_point(px, py)
                sx += vx
                sy += vy
            n = float(len(pts))
            return sx / n, sy / n

        return avg(self.left, left_pts), avg(self.right, right_pts)

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        for z, color in ((self.left, (80, 120, 200, 90)), (self.right, (200, 120, 80, 90))):
            s = pygame.Surface((int(z.radius * 2 + 4), int(z.radius * 2 + 4)), pygame.SRCALPHA)
            cx, cy = z.radius + 2, z.radius + 2
            pygame.draw.circle(s, color, (int(cx), int(cy)), int(z.radius))
            pygame.draw.circle(s, (255, 255, 255, 55), (int(cx), int(cy)), int(z.radius), 2)
            surf.blit(s, (int(z.center_x - z.radius - 2), int(z.center_y - z.radius - 2)))

        for rect, label in (
            (self.p1_interact, "P1 use"),
            (self.p2_interact, "P2 use"),
        ):
            overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            overlay.fill((40, 44, 58, 200))
            surf.blit(overlay, rect.topleft)
            pygame.draw.rect(surf, (200, 200, 220), rect, 2)
            t = font.render(label, True, (235, 235, 245))
            surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
