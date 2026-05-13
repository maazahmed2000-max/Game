# PSI Quantum — wafer lab (single player)

Overcooked-style **shift** on an isometric lab floor: receive wafers, load the prober, wait for cassette inventory, dial the right test (**E, O, EO, Oband, Cband, Other**), run the test chamber, rack finished lots. **Coworkers** patrol the aisle — bump them while carrying a wafer and you drop the lot and lose shift time.

## Run locally

```bash
pip install -r requirements.txt
python main.py
```

- **WASD** move · **Space** (or **Use** on touch) interact · **A / D** (or arrows) change test at the bench when prompted  
- **Esc** ends the shift early (returns to menu)

## Web build (pygbag)

```powershell
.\build_web.ps1
```

Then serve `build\web` over HTTP for testing. `constants.py` still defines unused `API_BASE_URL` for legacy tooling; the game no longer calls a multiplayer API.

## GitHub Pages

Push to `main` and use **Actions → Publish web game** as before. The wasm bundle is single-player only.
