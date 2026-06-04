# PSI Quantum — wafer lab (single player)

Overcooked-style **shift** on an isometric lab floor: receive wafers, load the prober, wait for cassette inventory, dial the right test (**E, O, EO, Oband, Cband, Other**), run the test chamber, rack finished lots. **Coworkers** patrol the aisle — bump them while carrying a wafer and you drop the lot and lose shift time.

## Clone and run

```bash
git clone https://github.com/maazahmed2000-max/Game.git
cd Game
pip install -r requirements.txt
python main.py
```

- **WASD** move · **Space** (or **Use** on touch) interact · **A / D** (or arrows) change test at the bench when prompted  
- **Esc** ends the shift early (returns to menu)

## Map layout (`dev_layout.json`)

Floor tiles, walls, prober position, and station hitboxes are stored in **`dev_layout.json`** (tracked in git so clones get the same lab).

- Toggle **Editor** (top) or press **M** to open the map editor  
- Edits auto-save to `dev_layout.json` (close the editor or wait ~1s)  
- **Tab** changes editor mode (tiles, zones, anchor, etc.)  
- **Anchor** mode: drag the center handle to move prober + floor together  
- **zone:…** modes: drag individual MHU / rack / chuck / load hitboxes  

Python helpers live in `dev_layout.py`; the editor UI is in `map_editor.py`.

## Web build (pygbag)

```powershell
.\build_web.ps1
```

Then serve `build\web` over HTTP (e.g. `py -m http.server 8000 --directory build\web`). The wasm build includes `dev_layout.json` from the repo root.

## GitHub Pages

Push to **`main`** — the **Publish web game** workflow builds and deploys to Pages.

1. Repo → **Settings** → **Pages** → **Build and deployment** → **Source: GitHub Actions**  
2. After a push, open **Actions** → latest **Publish web game** run → deployment URL  
   (typically `https://maazahmed2000-max.github.io/Game/`)

## Push updates

```powershell
git add -A
git commit -m "Your message"
git push origin main
```

Or use GitHub CLI (after `gh auth login`):

```powershell
.\complete_github.ps1
```
