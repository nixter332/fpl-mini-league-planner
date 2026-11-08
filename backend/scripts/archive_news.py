"""Save FPL's injury news for the upcoming deadline, so future backtests know what managers knew.

FPL only ever shows today's news, so it has to be saved as it happens. A scheduled GitHub
Action (.github/workflows/archive-news.yml) runs this every few hours; the last save before a
deadline is what managers saw. One file per gameweek: backend/data/news/gw{N}.json.

Usage (from backend/):  python -m scripts.archive_news
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.fpl.cache import DiskCache
from app.fpl.client import FPLClient
from app.fpl.gameweeks import next_actionable_gameweek
from app.fpl.models import Bootstrap

NEWS_DIR = Path(__file__).resolve().parents[1] / "data" / "news"
FIELDS = ("status", "news", "news_added", "chance_of_playing_next_round", "chance_of_playing_this_round")


def snapshot(bootstrap: Bootstrap, now: datetime) -> dict[str, Any] | None:
    """Every player's availability for the next deadline; None after the season's last deadline."""
    event = next_actionable_gameweek(bootstrap.events, now)
    if event is None:
        return None
    players = {}
    for e in sorted(bootstrap.elements, key=lambda e: e.id):
        row = {f: getattr(e, f) for f in FIELDS}
        row["news_added"] = row["news_added"].isoformat() if row["news_added"] else None
        players[str(e.id)] = row
    return {"gw": event.id, "deadline": event.deadline_time.isoformat(), "captured_at": now.isoformat(), "players": players}


def save(snap: dict[str, Any], folder: Path = NEWS_DIR) -> Path | None:
    """Write gw{N}.json; skip if the players' news is unchanged (so the Action commits only changes)."""
    path = folder / f"gw{snap['gw']}.json"
    try:
        if json.loads(path.read_text(encoding="utf-8"))["players"] == snap["players"]:
            return None
    except (OSError, ValueError, KeyError):
        pass
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as tmp, FPLClient(DiskCache(Path(tmp))) as client:  # always fresh
        bootstrap = Bootstrap.model_validate(client.bootstrap())
    snap = snapshot(bootstrap, now)
    if snap is None:
        print("No deadline left this season.")
        return
    path = save(snap)
    flagged = sum(1 for p in snap["players"].values() if p["status"] != "a")
    print(f"GW{snap['gw']}: {flagged} players flagged; " + (f"saved {path.name}" if path else "unchanged"))


if __name__ == "__main__":
    sys.exit(main())
