from pathlib import Path

from app.fpl.cache import DiskCache


class FakeClock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_miss_then_hit(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path, clock=FakeClock())
    assert cache.get("bootstrap-static") is None
    cache.set("bootstrap-static", {"events": [1, 2]}, ttl=60)
    assert cache.get("bootstrap-static") == {"events": [1, 2]}


def test_ttl_expiry(tmp_path: Path) -> None:
    clock = FakeClock()
    cache = DiskCache(tmp_path, clock=clock)
    cache.set("entry-1", {"id": 1}, ttl=900)
    clock.t += 899
    assert cache.get("entry-1") == {"id": 1}
    clock.t += 1
    assert cache.get("entry-1") is None


def test_earlier_of_ttl_and_deadline_wins(tmp_path: Path) -> None:
    clock = FakeClock()
    cache = DiskCache(tmp_path, clock=clock)
    cache.set("bootstrap-static", {"a": 1}, ttl=6 * 3600, expires_at=clock.t + 60)
    clock.t += 60
    assert cache.get("bootstrap-static") is None

    cache.set("fixtures", [1], ttl=60, expires_at=clock.t + 6 * 3600)
    clock.t += 60
    assert cache.get("fixtures") is None


def test_no_expiry_lasts_forever(tmp_path: Path) -> None:
    clock = FakeClock()
    cache = DiskCache(tmp_path, clock=clock)
    cache.set("event-9-live", {"elements": []})
    clock.t += 10 * 365 * 86400
    assert cache.get("event-9-live") == {"elements": []}


def test_persists_across_instances(tmp_path: Path) -> None:
    DiskCache(tmp_path).set("k", [1, 2, 3], ttl=60)
    assert DiskCache(tmp_path).get("k") == [1, 2, 3]


def test_corrupt_file_is_a_miss(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("k", 1, ttl=60)
    cache.path_for("k").write_text("{not json", encoding="utf-8")
    assert cache.get("k") is None


def test_keys_become_safe_filenames(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    path = cache.path_for("../entry/5/event/10?x=1")
    assert path.parent == tmp_path
    assert path.name == "entry_5_event_10_x_1.json"


def test_clear(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None and cache.get("b") is None
