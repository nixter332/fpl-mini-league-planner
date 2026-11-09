"""Anonymous feedback from the app is accepted, size-limited and logged."""

import logging

from fastapi.testclient import TestClient

from app.api.main import app


def test_feedback_is_logged(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="feedback"):
        r = TestClient(app).post("/api/feedback", json={
            "kind": "plan", "useful": False, "text": "Captain pick looks odd",
            "context": {"page": "plans", "strategy": "protect", "horizon": 4, "rank": 1, "gw": 11},
        })
    assert r.status_code == 200 and r.json() == {"ok": True}
    line = next(rec.getMessage() for rec in caplog.records if rec.name == "feedback")
    assert "Captain pick looks odd" in line and '"rank": 1' in line


def test_feedback_is_validated() -> None:
    client = TestClient(app)
    assert client.post("/api/feedback", json={"kind": "spam"}).status_code == 422
    assert client.post("/api/feedback", json={"kind": "general", "text": "x" * 1001}).status_code == 422
