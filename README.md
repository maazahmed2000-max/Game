# Kitchen Rush (co-op prototype)

Python + **pygame-ce** isometric kitchen game: **one player per device**. A friend **joins online** with a **username** and **room code** from the lobby (no shared keyboard).

The **game logic runs on a small FastAPI server**; the pygame app is a thin client (HTTP). The **browser build** still uses [pygbag](https://github.com/pygame-web/pygbag).

## 1) Run the game server (required)

From the repo root:

```bash
pip install -r server/requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8765
```

Deploy the same app to **Render**, **Railway**, **Fly.io**, etc. (see `Procfile`). You need a **public https URL** for the web build on GitHub Pages.

## 2) Run the client (PC)

```bash
pip install -r requirements.txt
python main.py
```

By default the client talks to `http://127.0.0.1:8765`. To point elsewhere:

```powershell
$env:GAME_API_URL="https://your-api.onrender.com"; python main.py
```

For a **pygbag / GitHub Pages** build, set `API_BASE_URL` in `constants.py` to that **https** URL before running `build_web.ps1` (browsers block mixed content).

## 3) Play flow

1. Host: **Host game** → enter name → **Create** → share the **room code**.
2. Guest (other device): **Join** → enter **username** + code → **Join game**.
3. Each device uses **WASD + Space** (or **stick + Use** on touch).

## Build the web version locally

```powershell
.\build_web.ps1
py -m http.server 8000 --directory .\build\web
```

## GitHub Pages

Push to `main`, enable **Pages → GitHub Actions**. The workflow publishes `build/web` only; **you still host the API separately** and set `API_BASE_URL` in `constants.py` for the wasm bundle.

## First-time GitHub push

Use **`.\complete_github.ps1`** (after `gh auth login`) or GitHub Desktop, as in earlier setup notes.
