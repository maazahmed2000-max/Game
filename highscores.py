"""Per-name best wafer counts — JSON on desktop, localStorage on web."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCORES_PATH = Path(__file__).resolve().parent / "highscores.json"
STORAGE_KEY = "psi_quantum_highscores"
MAX_NAME_LEN = 24
MAX_LEADERBOARD = 10


@dataclass
class ScoreEntry:
    name: str
    wafers: int
    when: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "ScoreEntry":
        return cls(
            name=str(raw.get("name", "")),
            wafers=int(raw.get("wafers", 0)),
            when=str(raw.get("when", "")),
        )


def normalize_name(name: str) -> str:
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        return "Operator"
    return cleaned[:MAX_NAME_LEN]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_raw() -> Dict[str, dict]:
    blob = _read_storage()
    if not blob:
        return {}
    by_name = blob.get("by_name")
    if not isinstance(by_name, dict):
        return {}
    return {str(k): v for k, v in by_name.items() if isinstance(v, dict)}


def _read_storage() -> Optional[dict]:
    if sys.platform == "emscripten":
        try:
            import platform

            raw = platform.window.localStorage.getItem(STORAGE_KEY)
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    if not SCORES_PATH.is_file():
        return None
    try:
        data = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_storage(by_name: Dict[str, dict]) -> None:
    payload = {"by_name": by_name}
    text = json.dumps(payload, indent=2)
    if sys.platform == "emscripten":
        try:
            import platform

            platform.window.localStorage.setItem(STORAGE_KEY, text)
        except Exception:
            pass
        return
    try:
        SCORES_PATH.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass


def load_scores() -> Dict[str, ScoreEntry]:
    raw = _load_raw()
    out: Dict[str, ScoreEntry] = {}
    for key, item in raw.items():
        entry = ScoreEntry.from_dict(item)
        name = normalize_name(entry.name or key)
        entry.name = name
        if entry.wafers > 0:
            out[name] = entry
    return out


def best_for_name(name: str) -> Optional[int]:
    entry = load_scores().get(normalize_name(name))
    return entry.wafers if entry else None


def top_scores(limit: int = MAX_LEADERBOARD) -> List[ScoreEntry]:
    entries = list(load_scores().values())
    entries.sort(key=lambda e: (-e.wafers, e.name.lower()))
    return entries[: max(1, limit)]


def submit_score(name: str, wafers: int) -> Tuple[bool, int]:
    """Save if personal best; returns (is_new_best, previous_best)."""
    name = normalize_name(name)
    wafers = max(0, int(wafers))
    raw = _load_raw()
    prev = 0
    if name in raw:
        prev = int(raw[name].get("wafers", 0))
    if wafers <= prev:
        return False, prev
    raw[name] = {
        "name": name,
        "wafers": wafers,
        "when": _now_iso(),
    }
    _write_storage(raw)
    return True, prev
