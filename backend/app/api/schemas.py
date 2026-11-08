"""API response shapes. Prices are ints in tenths of a million; the frontend formats them."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Kit(BaseModel):
    body: str
    sleeve: str
    trim: str


class Club(BaseModel):
    id: int
    short_name: str
    name: str
    kit: Kit


class Member(BaseModel):
    entry: int
    player_name: str
    entry_name: str
    rank: int
    total: int


class ResolveResponse(BaseModel):
    # choice: a bare number that is both a team and a league; the user picks which they meant
    type: Literal["team", "league", "choice"]
    id: int
    team_name: str | None = None  # for "choice"
    manager_name: str | None = None
    league_name: str | None = None
    members: list[Member] = []
    more_members: bool = False  # the league has more than one page of standings


class Gameweek(BaseModel):
    id: int
    name: str
    deadline: datetime


class PlayerGw(BaseModel):
    gw: int
    fixture: str  # "LEE (H)", "LEE (H), NEW (A)" in a double, "—" in a blank
    xpts: float


class Player(BaseModel):
    id: int
    name: str
    position: Literal["GKP", "DEF", "MID", "FWD"]
    club: str  # short name; look up the kit in `clubs`
    price: int
    sell_price: int | None = None  # only for players in the user's squad
    status: str
    news: str
    doubtful: bool  # show the "!" flag
    rivals_owned: int  # rivals with him in their 15
    rivals_captained: int = 0  # rivals who captained him in the GW their picks are from
    gws: list[PlayerGw]


class LineupGw(BaseModel):
    gw: int
    starting: list[int]
    bench: list[int]
    captain: int
    vice: int
    xpts: float  # XI + captain
    rivals_avg: float | None = None
    edge: float | None = None


class LeagueInfo(BaseModel):
    id: int
    name: str
    size: int | None = None  # managers in the league


class Standing(BaseModel):
    league: LeagueInfo
    rank: int | None
    total: int | None
    leader_name: str | None
    leader_entry_name: str | None
    gap_to_first: int | None  # positive = points behind 1st; 0 if you're 1st
    n_rivals: int


ChipName = Literal["wildcard", "freehit", "bboost", "3xc"]


class ChipLeft(BaseModel):
    name: ChipName
    label: str  # "Bench Boost"
    start: int  # first GW it can be played
    stop: int  # last GW (lost after this)


class RivalsProgress(BaseModel):
    league_id: int
    loaded: int  # rivals whose squads are loaded
    total: int
    ready: bool


class TeamResponse(BaseModel):
    entry: int
    team_name: str
    manager_name: str
    picks_gw: int
    free_transfers: int
    bank: int
    leagues: list[LeagueInfo]  # private classic leagues, for the switcher
    standing: Standing | None
    rivals: RivalsProgress | None = None  # None = no league; ready=False = still loading
    gameweeks: list[Gameweek]
    lineups: list[LineupGw]
    squad: list[int]
    players: dict[int, Player]
    clubs: dict[str, Club]
    facts: list[str]
    chips_left: list[ChipLeft] = []


class Move(BaseModel):
    player_out: int
    player_in: int
    out_price: int  # what selling raises
    in_price: int


class PlanGw(BaseModel):
    gw: int
    moves: list[Move]  # with a Free Hit: this week's one-off changes (the squad reverts after)
    hits: int
    free_transfers: int
    bank: int
    captain: int
    vice: int
    chip: ChipName | None = None
    chip_xpts: float | None = None  # expected points the chip adds (Bench Boost: the bench; Triple Captain: the captain again)


class Threat(BaseModel):
    player: int
    rivals_starting: int
    xpts: float


class HeadToHead(BaseModel):
    opponent_name: str
    opponent_entry_name: str
    opponent_rank: int
    points_gap: int  # positive = they're ahead
    you_xpts: float
    them_xpts: float
    shared_players: int
    your_differentials: list[int]
    their_differentials: list[int]
    their_captain: int


class Plan(BaseModel):
    rank: int
    tag: Literal["free", "hit", "roll"]
    is_roll: bool
    proven_optimal: bool
    hits: int
    xpts: float
    xpts_gain: float  # includes chip points
    chip_xpts: float = 0.0  # the part of xpts_gain that comes from chips
    differential_gain: float
    summary: str
    gameweeks: list[PlanGw]
    before: LineupGw
    after: LineupGw
    threats: list[Threat]
    head_to_head: HeadToHead | None


class PlansResponse(BaseModel):
    entry: int
    strategy: Literal["protect", "balanced", "risky"]
    horizon: int
    max_hits: int
    chips_left: list[ChipLeft] = []
    wildcard_gw: int | None = None  # the user chose to play these
    freehit_gw: int | None = None
    auto_chips: bool = True  # the planner may play Bench Boost / Triple Captain
    gws: list[int]
    free_transfers: int
    bank: int
    standing: Standing | None
    captain_note: str
    plans: list[Plan]
    players: dict[int, Player]
    clubs: dict[str, Club]
    facts: list[str]
    seconds: float


class ExplainResponse(BaseModel):
    rank: int
    status: Literal["ok", "unavailable", "off"]  # off = no API key configured
    why: str | None = None
    watch_out: str | None = None


class ChipAdvice(BaseModel):
    """What playing a Wildcard or Free Hit this week would add, from the optimizer."""

    chip: ChipName
    label: str
    gw: int
    xpts_gain: float  # the best plan with the chip, vs no transfers
    vs_best_plan: float  # minus the best plan without it (over the horizon only)
