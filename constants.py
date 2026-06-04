"""Screen and gameplay tuning — tweak here first."""

TILE = 48
# Wide floor plan (corridor + bays), blueprint-style
COLS = 28
ROWS = 20
SCREEN_W = 1280
SCREEN_H = 760
FPS = 60

BG = (12, 14, 18)
FLOOR = (18, 20, 26)
PLAN_LINE = (200, 205, 220)
WALL = (28, 30, 38)
LAB_TECH = (210, 222, 240)
HIGHLIGHT = (255, 228, 120)

SHIFT_SECONDS = 180
INVENTORY_WAIT_S = 2.6
CHAMBER_RUN_MIN_S = 10.0
CHAMBER_RUN_MAX_S = 22.0

# Chuck idle penalty: every 20s on standby costs 5s off the shift timer (after first wafer arrives).
CHUCK_STANDBY_PENALTY_INTERVAL_S = 20.0
CHUCK_STANDBY_PENALTY_S = 5.0
CHUCK_STANDBY_NOTICE_S = 6.0

# New wafer lots every 10–15 s (randomized)
SPAWN_MIN_S = 10.0
SPAWN_MAX_S = 15.0
MAX_WAFER_QUEUE = 6

# HUD / world progress bar widths (pixels)
HUD_PROGRESS_BAR_W = 200
WORLD_PROGRESS_BAR_W = 110
HUD_PANEL_WIDTH = 220

# Overlay walkable tiles when editor toggle is on (see in-game Editor switch).
DEBUG_DRAW_WALKABLE = False

# Dev-only: drag-edit walls, blocks, and zone hitboxes (M toggle, S save). Off for release builds.
DEBUG_MAP_EDITOR = True
