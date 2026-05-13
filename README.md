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

## Push to GitHub (you already have this folder)

Your code is committed on branch **`main`** locally. If it is not on GitHub yet:

1. Open **GitHub Desktop** → **File → Add local repository** → choose `C:\Users\maaza\Documents\GitHub\Game` (or open it if it is already listed).
2. Click **Publish repository** *or* **Push origin** (depending on whether GitHub already has an empty `Game` repo).
3. If GitHub says the remote does not exist, create a **public** repo named **`Game`** on your account first, then set the remote in this folder:
   `git remote set-url origin https://github.com/<YOUR_USERNAME>/Game.git`

## Enable the playable web build (GitHub Pages)

After the first successful push: **Settings → Pages → Build and deployment → Source: GitHub Actions**.  
Wait for the **Publish web game** workflow, then open the **Pages** URL from the workflow run (often `https://<username>.github.io/Game/`).

### Alternate: GitHub CLI

From this folder: `gh auth login` then `git push -u origin main`, or run **`.\complete_github.ps1`** only if you still need to create the repo from scratch.

If the default remote URL is wrong for your account, run:

`git remote set-url origin https://github.com/<YOUR_USERNAME>/Game.git`
