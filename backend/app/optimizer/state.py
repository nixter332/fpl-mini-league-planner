"""A manager's squad as of the last deadline: players, purchase/sell prices, bank, free transfers.

The public picks endpoint has no purchase prices, so they're derived from the transfer
history (see docs/fpl-api-notes.md). Transfers made since the last deadline aren't visible.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.fpl.models import ChipDef, Element, EntryHistory, EntryPicks, Transfer
from app.optimizer.chips import ChipWindow, chips_left

MAX_FREE_TRANSFERS = 5
TRANSFER_CHIPS = {"wildcard", "freehit"}


@dataclass(frozen=True)
class OwnedPlayer:
    element: int
    purchase_price: int
    sell_price: int


@dataclass(frozen=True)
class SquadState:
    entry_id: int
    picks_gw: int  # the GW whose picks this squad comes from
    players: tuple[OwnedPlayer, ...]
    bank: int
    free_transfers: int  # available for the next actionable GW
    chips: tuple[ChipWindow, ...] = ()  # chips left, with the GWs each can be played in

    @property
    def element_ids(self) -> set[int]:
        return {p.element for p in self.players}

    def sell_price(self, element: int) -> int:
        return next(p.sell_price for p in self.players if p.element == element)


def sell_price(purchase: int, now: int, sell_on_fee: float = 0.5) -> int:
    """You keep half of any rise (rounded down to £0.1m) and lose all of any fall."""
    if now <= purchase:
        return now
    return purchase + int((now - purchase) * sell_on_fee)


def purchase_prices(
    squad: list[int], transfers: list[Transfer], history: EntryHistory, elements: dict[int, Element]
) -> dict[int, int]:
    """Latest buy price per player; players never transferred in were bought before GW1 at the
    start-of-season price. Free-hit transfers are ignored because the squad reverts afterwards."""
    free_hit_gws = {c.event for c in history.chips if c.name == "freehit"}
    latest: dict[int, int] = {}
    for t in sorted(transfers, key=lambda t: t.time):
        if t.event not in free_hit_gws:
            latest[t.element_in] = t.element_in_cost
    return {p: latest.get(p, elements[p].start_cost) for p in squad}


def free_transfers_after(history: EntryHistory, max_free: int = MAX_FREE_TRANSFERS) -> int:
    """Replay the history to get the free transfers available for the next GW.

    The first GW's transfers are unlimited (pre-season), leaving 1 for the next. After that,
    each GW: next = min(unused + 1, max). Wildcard and free-hit GWs keep the banked count
    without adding one (confirmed on Nikhil's GW6 wildcard + GW9 hit).
    """
    chips = {c.event: c.name for c in history.chips}
    rows = sorted(history.current, key=lambda r: r.event)
    ft = 0
    for i, row in enumerate(rows):
        if i == 0:
            ft = 1
            continue
        if chips.get(row.event) in TRANSFER_CHIPS:
            continue
        free_used = row.event_transfers - row.event_transfers_cost // 4
        ft = min(max(ft - free_used, 0) + 1, max_free)
    return ft


def build_state(
    entry_id: int,
    picks: EntryPicks,
    picks_gw: int,
    history: EntryHistory,
    transfers: list[Transfer],
    elements: dict[int, Element],
    sell_on_fee: float = 0.5,
    max_free: int = MAX_FREE_TRANSFERS,
    chip_defs: Iterable[ChipDef] = (),
) -> SquadState:
    """`picks` must be the manager's real squad: if the latest GW was a free hit, pass the
    previous GW's picks instead (the squad reverts)."""
    squad = [p.element for p in picks.picks]
    bought = purchase_prices(squad, transfers, history, elements)
    players = tuple(
        OwnedPlayer(p, bought[p], sell_price(bought[p], elements[p].now_cost, sell_on_fee)) for p in squad
    )
    return SquadState(
        entry_id=entry_id,
        picks_gw=picks_gw,
        players=players,
        bank=picks.entry_history.bank,
        free_transfers=free_transfers_after(history, max_free),
        chips=chips_left(chip_defs, history.chips, max((r.event for r in history.current), default=0) + 1),
    )
