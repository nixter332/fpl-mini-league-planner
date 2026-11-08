"""Saving injury news per deadline (no network: built from the saved bootstrap)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.fpl.models import Bootstrap
from scripts.archive_news import save, snapshot
from tests.conftest import load_fixture


def test_snapshot_is_for_the_next_deadline(manifest: dict[str, Any], snapshot_time: datetime) -> None:
    bootstrap = Bootstrap.model_validate(load_fixture(manifest["files"]["bootstrap"]))
    snap = snapshot(bootstrap, snapshot_time)
    assert snap["gw"] == manifest["latest_started_gw"] + 1
    assert len(snap["players"]) == len(bootstrap.elements)
    flagged = next(e for e in bootstrap.elements if e.status != "a")
    row = snap["players"][str(flagged.id)]
    assert row["status"] == flagged.status and row["news"] == flagged.news
    json.dumps(snap)  # plain JSON


def test_save_writes_only_changes(tmp_path: Path, manifest: dict[str, Any], snapshot_time: datetime) -> None:
    bootstrap = Bootstrap.model_validate(load_fixture(manifest["files"]["bootstrap"]))
    snap = snapshot(bootstrap, snapshot_time)
    path = save(snap, tmp_path)
    assert path is not None and path.name == f"gw{snap['gw']}.json"
    assert save({**snap, "captured_at": "later"}, tmp_path) is None  # same news: nothing to commit
    changed = json.loads(json.dumps(snap))
    first = next(iter(changed["players"]))
    changed["players"][first]["news"] = "Knee injury - Expected back 30 Nov"
    assert save(changed, tmp_path) == path
    assert json.loads(path.read_text(encoding="utf-8"))["players"][first]["news"].startswith("Knee")
