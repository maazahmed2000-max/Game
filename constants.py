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
CHAMBER_RUN_S = 3.1

# New wafer lots every 10–15 s (randomized)
SPAWN_MIN_S = 10.0
SPAWN_MAX_S = 15.0

# Overlay walkable tiles + station hitbox radii (toggle off for normal play).
DEBUG_DRAW_WALKABLE = True
