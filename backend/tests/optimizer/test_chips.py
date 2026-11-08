"""Which chips a manager has left, and when each can be played."""

from app.fpl.models import ChipDef, ChipPlay
from app.optimizer.chips import ChipWindow, chips_left, window_for

DEFS = [
    ChipDef(id=i, name=n, number=1, start_event=s, stop_event=e, chip_type="x")
    for i, (n, s, e) in enumerate(
        [("wildcard", 2, 19), ("wildcard", 20, 38), ("freehit", 2, 19), ("freehit", 20, 38),
         ("bboost", 1, 19), ("bboost", 20, 38), ("3xc", 1, 19), ("3xc", 20, 38)], start=1)
]


def test_used_chips_only_consume_their_own_half() -> None:
    played = [ChipPlay(name="3xc", event=3), ChipPlay(name="wildcard", event=6)]
    left = chips_left(DEFS, played, from_gw=11)
    first_half = {c.name for c in left if c.stop == 19}
    assert first_half == {"freehit", "bboost"}
    assert {c.name for c in left if c.stop == 38} == {"wildcard", "freehit", "bboost", "3xc"}
    assert ChipWindow("bboost", 11, 19) in left  # can't be played before the next deadline


def test_expired_windows_are_gone() -> None:
    left = chips_left(DEFS, [], from_gw=20)
    assert all(c.start >= 20 for c in left) and len(left) == 4


def test_window_for() -> None:
    left = chips_left(DEFS, [], from_gw=18)
    assert window_for(left, "bboost", 19) == ChipWindow("bboost", 18, 19)
    assert window_for(left, "bboost", 20) == ChipWindow("bboost", 20, 38)
    assert window_for(left, "wildcard", 17) is None


def test_real_squad_has_chips(manager_state) -> None:
    # Nikhil played Triple Captain (GW3) and Wildcard (GW6): Free Hit and Bench Boost are left
    # in the first half, and all four in the second.
    first = {c.name for c in manager_state.chips if c.stop <= 19}
    assert first == {"freehit", "bboost"}
    assert len([c for c in manager_state.chips if c.start >= 20]) == 4
