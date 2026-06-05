"""On-screen direction buttons + use button for one local player (mobile / web)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pygame

Vec2 = Tuple[float, float]
ButtonName = str


@dataclass
class SoloTouch:
    """D-pad style buttons (bottom left) + Use (bottom right)."""

    screen_w: int
    screen_h: int
    margin: float = 22.0
    button_size: int = 56
    display: object | None = None
    btn_up: pygame.Rect = field(init=False)
    btn_down: pygame.Rect = field(init=False)
    btn_left: pygame.Rect = field(init=False)
    btn_right: pygame.Rect = field(init=False)
    use_rect: pygame.Rect = field(init=False)
    _touch_button: Dict[int, ButtonName] = field(default_factory=dict)
    _pressed: set[ButtonName] = field(default_factory=set)
    _use_next: bool = False

    def __post_init__(self) -> None:
        self._layout_controls()

    def set_screen_size(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._layout_controls()

    def _layout_controls(self) -> None:
        m = self.margin
        bw = self.button_size
        cx = self.screen_w * 0.38
        cy = self.screen_h - m - bw * 1.5
        gap = 4
        self.btn_up = pygame.Rect(int(cx - bw // 2), int(cy - bw - gap), bw, bw)
        self.btn_down = pygame.Rect(int(cx - bw // 2), int(cy + gap), bw, bw)
        self.btn_left = pygame.Rect(int(cx - bw - gap), int(cy - bw // 2), bw, bw)
        self.btn_right = pygame.Rect(int(cx + gap), int(cy - bw // 2), bw, bw)
        uw, uh = 100, 48
        self.use_rect = pygame.Rect(int(self.screen_w - m - uw), int(cy - uh // 2), uw, uh)

    def _button_rects(self) -> List[Tuple[ButtonName, pygame.Rect]]:
        return [
            ("up", self.btn_up),
            ("down", self.btn_down),
            ("left", self.btn_left),
            ("right", self.btn_right),
            ("use", self.use_rect),
        ]

    def _pointer_pos(self, event: pygame.event.Event) -> tuple[float, float]:
        scaler = getattr(self.display, "scaler", None) if self.display is not None else None
        if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            if scaler is not None:
                return scaler.finger_to_logical(event.x, event.y)
            return event.x * self.screen_w, event.y * self.screen_h
        from display import logical_mouse_pos

        lx, ly = logical_mouse_pos(event.pos)
        return float(lx), float(ly)

    def _button_at(self, x: float, y: float) -> Optional[ButtonName]:
        for name, rect in self._button_rects():
            if rect.collidepoint(x, y):
                return name
        return None

    def _press_button(self, finger_id: int, name: ButtonName) -> None:
        self._touch_button[finger_id] = name
        if name == "use":
            self._use_next = True
        else:
            self._pressed.add(name)

    def _release_finger(self, finger_id: int) -> None:
        name = self._touch_button.pop(finger_id, None)
        if name and name != "use":
            self._pressed.discard(name)

    def handle_event(self, event: pygame.event.Event, *, ignore_mouse: bool = False) -> None:
        if ignore_mouse and event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
        ):
            return
        if event.type == pygame.FINGERDOWN:
            x, y = self._pointer_pos(event)
            btn = self._button_at(x, y)
            if btn is not None:
                self._press_button(event.finger_id, btn)
        elif event.type == pygame.FINGERMOTION:
            if event.finger_id not in self._touch_button:
                return
            old = self._touch_button[event.finger_id]
            if old != "use":
                self._pressed.discard(old)
            x, y = self._pointer_pos(event)
            btn = self._button_at(x, y)
            if btn is not None:
                self._press_button(event.finger_id, btn)
            else:
                self._touch_button.pop(event.finger_id, None)
        elif event.type == pygame.FINGERUP:
            self._release_finger(event.finger_id)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = self._pointer_pos(event)
            btn = self._button_at(x, y)
            if btn is not None:
                self._press_button(-1, btn)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._release_finger(-1)

    def pop_use(self) -> bool:
        u = self._use_next
        self._use_next = False
        return u

    def vector(self) -> Vec2:
        dx = dy = 0.0
        if "right" in self._pressed:
            dx += 1.0
        if "left" in self._pressed:
            dx -= 1.0
        if "down" in self._pressed:
            dy += 1.0
        if "up" in self._pressed:
            dy -= 1.0
        mag = math.hypot(dx, dy)
        if mag > 1.0:
            dx /= mag
            dy /= mag
        return dx, dy

    def _draw_button(
        self,
        surf: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        font: pygame.font.Font,
        *,
        pressed: bool,
    ) -> None:
        overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        fill = (70, 110, 180, 170) if pressed else (40, 44, 58, 200)
        overlay.fill(fill)
        surf.blit(overlay, rect.topleft)
        border = (140, 180, 255) if pressed else (200, 200, 220)
        pygame.draw.rect(surf, border, rect, 2, border_radius=6)
        t = font.render(label, True, (235, 235, 245))
        surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        self._draw_button(surf, self.btn_up, "▲", font, pressed="up" in self._pressed)
        self._draw_button(surf, self.btn_down, "▼", font, pressed="down" in self._pressed)
        self._draw_button(surf, self.btn_left, "◀", font, pressed="left" in self._pressed)
        self._draw_button(surf, self.btn_right, "▶", font, pressed="right" in self._pressed)
        self._draw_button(surf, self.use_rect, "Use", font, pressed=False)
