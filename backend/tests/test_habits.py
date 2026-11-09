"""Manager habits from FPL history."""

from app.fpl.models import ChipPlay, EntryHistory, HistoryEvent
from app.model.habits import habits


def row(gw: int, points: int, transfers: int, cost: int) -> HistoryEvent:
    return HistoryEvent(event=gw, points=points, total_points=0, overall_rank=None, bank=0, value=1000,
                        event_transfers=transfers, event_transfers_cost=cost, points_on_bench=0)


def test_habits_leave_out_wildcard_weeks() -> None:
    history = EntryHistory(
        current=[row(2, 50, 1, 0), row(3, 60, 0, 0), row(4, 40, 0, 0), row(5, 70, 3, 8)],
        chips=[ChipPlay(name="wildcard", event=4), ChipPlay(name="bboost", event=25)],
    )
    h = habits(history, 2, 5)
    assert h.weeks == 3  # GW4 was a Wildcard
    assert h.points_per_gw == (50 + 60 + 40 + 62) / 4
    assert h.transfers_per_gw == (1 + 0 + 3) / 3
    assert h.hits_per_gw == 2 / 3
    assert h.roll_share == 1 / 3
    assert h.chips == {"wildcard": 4}  # second-half chips aren't counted
