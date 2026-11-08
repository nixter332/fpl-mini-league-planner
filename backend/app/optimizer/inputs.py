"""Assemble optimizer inputs: the manager's state, rivals' picks and the pruned player pool."""

from collections.abc import Collection, Sequence
from datetime import datetime

import pandas as pd

from app.fpl.client import FPLClient
from app.fpl.gameweeks import latest_started_gameweek
from app.fpl.models import Bootstrap, EntryHistory, EntryPicks, LeagueStandings, Transfer
from app.model.scoring import DEF, FWD, GKP, MID
from app.optimizer.solver import PoolPlayer
from app.optimizer.state import SquadState, build_state

# Top N per position by horizon xPts, plus the cheapest few available (bench fodder).
POOL_SIZES = {GKP: 10, DEF: 30, MID: 30, FWD: 20}
CHEAPEST_PER_POSITION = 3


def build_pool(
    bootstrap: Bootstrap,
    projection: pd.DataFrame,
    state: SquadState,
    gws: Sequence[int],
    *,
    sizes: dict[int, int] = POOL_SIZES,
    cheapest: int = CHEAPEST_PER_POSITION,
    available: Collection[int] | None = None,
) -> list[PoolPlayer]:
    """Current squad + the best and cheapest buyable players per position.

    `available` (backtests): the players who existed in the game at that deadline. Today's
    status would leak the future, so it replaces the status checks."""
    owned = state.element_ids
    totals = projection[projection.index.get_level_values("gw").isin(gws)].groupby("element")["xpts"].sum()
    if available is None:
        buyable = [e for e in bootstrap.elements if e.status != "u" and e.can_transact]
    else:
        buyable = [e for e in bootstrap.elements if e.id in available]

    chosen = set(owned)
    for pos, n in sizes.items():
        in_pos = [e for e in buyable if e.element_type == pos]
        chosen.update(e.id for e in sorted(in_pos, key=lambda e: -totals.get(e.id, 0.0))[:n])
        fit_cheap = [e for e in in_pos if e.status == "a" or available is not None]
        chosen.update(e.id for e in sorted(fit_cheap, key=lambda e: (e.now_cost, -totals.get(e.id, 0.0)))[:cheapest])

    sell = {p.element: p.sell_price for p in state.players}
    pool = []
    for e in bootstrap.elements:
        if e.id not in chosen:
            continue
        xpts = {gw: float(projection.loc[(e.id, gw), "xpts"]) if (e.id, gw) in projection.index else 0.0 for gw in gws}
        pool.append(PoolPlayer(e.id, e.element_type, e.team, e.now_cost, sell.get(e.id, e.now_cost), xpts))
    return pool


def load_state(client: FPLClient, entry_id: int, bootstrap: Bootstrap, now: datetime) -> SquadState:
    """The squad as of the last deadline. If that GW was a free hit, use the GW before it
    (the squad reverts after a free hit)."""
    started = latest_started_gameweek(bootstrap.events, now)
    if started is None:
        raise ValueError("The season hasn't started; there are no picks yet.")
    gw = started.id
    picks = EntryPicks.model_validate(client.entry_picks(entry_id, gw))
    if picks.active_chip == "freehit" and gw > 1:
        gw -= 1
        picks = EntryPicks.model_validate(client.entry_picks(entry_id, gw))
    history = EntryHistory.model_validate(client.entry_history(entry_id))
    transfers = [Transfer.model_validate(t) for t in client.entry_transfers(entry_id)]
    elements = {e.id: e for e in bootstrap.elements}
    rules = bootstrap.game_config.rules
    return build_state(entry_id, picks, gw, history, transfers, elements,
                       rules.transfers_sell_on_fee, rules.max_extra_free_transfers + 1, bootstrap.chips)


def top_rivals(client: FPLClient, league_id: int, entry_id: int, n: int = 20) -> list[int]:
    """The top `n` managers in the league by rank, excluding the user."""
    pages = [LeagueStandings.model_validate(p) for p in client.league_standings_all(league_id)]
    rows = sorted((r for page in pages for r in page.standings.results), key=lambda r: r.rank)
    return [r.entry for r in rows if r.entry != entry_id][:n]


def load_rival_picks(client: FPLClient, rival_ids: Sequence[int], gw: int) -> list[EntryPicks]:
    """Rivals' picks for `gw` (throttled bulk fetch; cached)."""
    raw = client.many_entry_picks(rival_ids, gw)
    return [EntryPicks.model_validate(v) for v in raw.values() if v is not None]
