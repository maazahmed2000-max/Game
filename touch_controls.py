"""On-screen stick + use button for one local player (mobile / web)."""

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
class SoloTouch:
    """One virtual stick (bottom center) + Use (for the only local player)."""

    screen_w: int
    screen_h: int
    margin: float = 22.0
    radius: float = 78.0
    display: object | None = None
    stick: StickZone = field(init=False)
    use_rect: pygame.Rect = field(init=False)
    _touch: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    _mouse_left: bool = False
    _use_next: bool = False

    def __post_init__(self) -> None:
        self._layout_controls()

    def set_screen_size(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._layout_controls()

    def _layout_controls(self) -> None:
        r = self.radius
        m = self.margin
        cx = self.screen_w * 0.5
        cy = self.screen_h - m - r
        self.stick = StickZone(cx, cy, r)
        uw, uh = 100, 48
        self.use_rect = pygame.Rect(int(cx + r + m), int(cy - uh * 0.5), uw, uh)

    def _pointer_pos(self, event: pygame.event.Event) -> tuple[float, float]:
        scaler = getattr(self.display, "scaler", None) if self.display is not None else None
        if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            if scaler is not None:
                return scaler.finger_to_logical(event.x, event.y)
            return event.x * self.screen_w, event.y * self.screen_h
        from display import logical_mouse_pos

        lx, ly = logical_mouse_pos(event.pos)
        return float(lx), float(ly)

    def handle_event(self, event: pygame.event.Event, *, ignore_mouse: bool = False) -> None:
        if ignore_mouse and event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
        ):
            return
        if event.type == pygame.FINGERDOWN:
            x, y = self._pointer_pos(event)
            self._touch[event.finger_id] = (x, y)
            self._try_use_tap(x, y)
        elif event.type == pygame.FINGERMOTION:
            if event.finger_id in self._touch:
                x, y = self._pointer_pos(event)
                self._touch[event.finger_id] = (x, y)
        elif event.type == pygame.FINGERUP:
            self._touch.pop(event.finger_id, None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_left = True
            x, y = self._pointer_pos(event)
            self._touch[-1] = (x, y)
            self._try_use_tap(x, y)
        elif event.type == pygame.MOUSEMOTION and self._mouse_left:
            x, y = self._pointer_pos(event)
            self._touch[-1] = (x, y)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_left = False
            self._touch.pop(-1, None)

    def _try_use_tap(self, x: float, y: float) -> None:
        if self.use_rect.collidepoint(x, y):
            self._use_next = True

    def pop_use(self) -> bool:
        u = self._use_next
        self._use_next = False
        return u

    def vector(self) -> Vec2:
        pts: List[Tuple[float, float]] = []
        reach = self.radius * 1.3
        for px, py in self._touch.values():
            if math.hypot(px - self.stick.center_x, py - self.stick.center_y) <= reach:
                pts.append((px, py))

        if not pts:
            return 0.0, 0.0
        sx = sy = 0.0
        for px, py in pts:
            vx, vy = self.stick.vec_from_point(px, py)
            sx += vx
            sy += vy
        n = float(len(pts))
        return sx / n, sy / n

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        z = self.stick
        s = pygame.Surface((int(z.radius * 2 + 4), int(z.radius * 2 + 4)), pygame.SRCALPHA)
        cx, cy = z.radius + 2, z.radius + 2
        pygame.draw.circle(s, (80, 120, 200, 90), (int(cx), int(cy)), int(z.radius))
        pygame.draw.circle(s, (255, 255, 255, 55), (int(cx), int(cy)), int(z.radius), 2)
        surf.blit(s, (int(z.center_x - z.radius - 2), int(z.center_y - z.radius - 2)))

        overlay = pygame.Surface((self.use_rect.w, self.use_rect.h), pygame.SRCALPHA)
        overlay.fill((40, 44, 58, 200))
        surf.blit(overlay, self.use_rect.topleft)
        pygame.draw.rect(surf, (200, 200, 220), self.use_rect, 2)
        t = font.render("Use", True, (235, 235, 245))
        surf.blit(t, (self.use_rect.centerx - t.get_width() // 2, self.use_rect.centery - t.get_height() // 2))
