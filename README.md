# Kitchen Rush (co-op prototype)

Python + **pygame-ce** kitchen game with isometric view, two players, and a **browser build** via [pygbag](https://github.com/pygame-web/pygbag).

## Play in the browser (after GitHub Pages deploy)

Push to `main`, then in the repo go to **Settings → Pages → Source: GitHub Actions**.  
When the **Publish web game** workflow finishes, open the **Pages** URL from the workflow summary (usually `https://<your-username>.github.io/<repo>/`).

## Run on your PC

```bash
pip install -r requirements.txt
python main.py
```

## Build the web version locally

```powershell
.\build_web.ps1
py -m http.server 8000 --directory .\build\web
```

Open `http://localhost:8000` (on your phone, use your PC’s LAN IP instead of `localhost`).

## Put this on GitHub (first time)

1. Install [GitHub CLI](https://cli.github.com/) if you do not have it (`winget install GitHub.cli`).
2. In this folder, run **`.\complete_github.ps1`** (PowerShell). It opens a browser to log in if needed, then creates the repo and pushes.
3. On GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

If the default repo name is taken, edit `REPO_NAME` in `scripts\push_to_github.ps1` and run `.\complete_github.ps1` again (or run `.\scripts\push_to_github.ps1` after `gh auth login`).
