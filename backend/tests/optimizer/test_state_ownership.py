from datetime import datetime, timezone

import pytest

from app.fpl.models import ChipPlay, EntryHistory, EntryPicks, HistoryEvent, Pick, Transfer
from app.optimizer.ownership import league_ownership
from app.optimizer.state import SquadState, free_transfers_after, purchase_prices, sell_price
from app.model.history import SeasonData

HAALAND = 411


# ---- sell prices --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "purchase, now, expected",
    [(100, 100, 100), (100, 104, 102), (100, 105, 102), (100, 101, 100), (100, 97, 97), (155, 158, 156)],
)
def test_sell_price_keeps_half_of_a_rise_and_all_of_a_fall(purchase: int, now: int, expected: int) -> None:
    assert sell_price(purchase, now) == expected


def test_nikhils_state(manager_state: SquadState) -> None:
    assert len(manager_state.players) == 15
    assert manager_state.bank == 11
    assert manager_state.free_transfers == 2  # confirmed by Nikhil in the FPL app
    assert manager_state.sell_price(HAALAND) == 156  # held since GW1 at 15.5, now 15.8
    assert sum(p.sell_price for p in manager_state.players) == 995


def test_players_held_since_gw1_use_the_start_price(season: SeasonData, manager_state: SquadState) -> None:
    haaland = next(e for e in season.bootstrap.elements if e.id == HAALAND)
    owned = next(p for p in manager_state.players if p.element == HAALAND)
    assert owned.purchase_price == haaland.start_cost == 155


def _transfer(gw: int, el_in: int, cost: int, day: int) -> Transfer:
    return Transfer(element_in=el_in, element_in_cost=cost, element_out=999, element_out_cost=50, event=gw,
                    time=datetime(2026, 9, day, tzinfo=timezone.utc))


def test_latest_buy_wins_and_free_hit_transfers_are_ignored(season: SeasonData) -> None:
    elements = {e.id: e for e in season.bootstrap.elements}
    player = next(iter(elements))
    transfers = [_transfer(3, player, 60, 1), _transfer(5, player, 64, 10), _transfer(7, player, 70, 20)]
    history = EntryHistory(current=[], chips=[ChipPlay(name="freehit", event=7)])
    assert purchase_prices([player], transfers, history, elements)[player] == 64


# ---- free transfers -----------------------------------------------------------------------


def _gw(event: int, transfers: int = 0, cost: int = 0) -> HistoryEvent:
    return HistoryEvent(event=event, points=50, total_points=50 * event, overall_rank=1, bank=0, value=1000,
                        event_transfers=transfers, event_transfers_cost=cost, points_on_bench=0)


def test_free_transfers_roll_and_cap_at_five() -> None:
    history = EntryHistory(current=[_gw(g) for g in range(1, 10)], chips=[])
    assert free_transfers_after(history) == 5
    assert free_transfers_after(EntryHistory(current=[_gw(1), _gw(2)], chips=[])) == 2


def test_a_hit_leaves_one_free_transfer() -> None:
    history = EntryHistory(current=[_gw(1), _gw(2), _gw(3, transfers=3, cost=4)], chips=[])
    assert free_transfers_after(history) == 1


def test_wildcard_keeps_banked_transfers_without_adding_one() -> None:
    history = EntryHistory(current=[_gw(1), _gw(2), _gw(3, transfers=12)], chips=[ChipPlay(name="wildcard", event=3)])
    assert free_transfers_after(history) == 2


def test_late_joiner_gets_one_after_their_first_gw() -> None:
    history = EntryHistory(current=[_gw(5, transfers=3)], chips=[])
    assert free_transfers_after(history) == 1


# ---- league ownership ---------------------------------------------------------------------


def _picks(*multipliers: tuple[int, int]) -> EntryPicks:
    picks = [Pick(element=e, position=i + 1, multiplier=m, is_captain=m >= 2, is_vice_captain=False)
             for i, (e, m) in enumerate(multipliers)]
    return EntryPicks(active_chip=None, picks=picks, entry_history=_gw(10))


def test_ownership_splits_starting_and_captaincy() -> None:
    rivals = [_picks((1, 2), (2, 1), (3, 0)), _picks((1, 1), (2, 3), (3, 0)), _picks((1, 1), (4, 2))]
    own = league_ownership(rivals)
    assert own.n_rivals == 3
    assert own.start_share(1) == 1.0 and own.captain_share(1) == pytest.approx(1 / 3)
    assert own.start_share(2) == pytest.approx(2 / 3) and own.captain_share(2) == pytest.approx(1 / 3)
    assert own.start_share(3) == 0  # benched
    assert own.eo[2] == pytest.approx(4 / 3)  # classic EO counts the triple captain 3x
    assert own.start_share(99) == 0


def test_real_rivals(rival_picks: list[EntryPicks]) -> None:
    own = league_ownership(rival_picks)
    assert own.n_rivals == len(rival_picks)
    assert all(0 <= v <= 1 for v in [*own.start.values(), *own.captain.values()])
    assert sum(own.captain.values()) == pytest.approx(1.0)  # every rival has exactly one captain
