"""Screen and gameplay tuning — tweak here first."""

import os

TILE = 48
COLS, ROWS = 14, 10
SCREEN_W = 1180
SCREEN_H = 720
FPS = 60

BG = (28, 32, 44)
FLOOR = (58, 64, 82)
WALL = (38, 42, 56)
PLAYER1 = (220, 120, 90)
PLAYER2 = (90, 160, 220)
HIGHLIGHT = (255, 230, 120)

# Multiplayer API (FastAPI server). For GitHub Pages builds, set this to your public https URL before running pygbag.
API_BASE_URL = os.environ.get("GAME_API_URL", "http://127.0.0.1:8765").rstrip("/")
