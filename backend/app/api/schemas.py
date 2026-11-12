"""API response shapes. Prices are ints in tenths of a million; the frontend formats them."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    difficulty: list[int] = []  # FPL's 1 (easy) to 5 (hard) per fixture, in the label's order


class Player(BaseModel):
    id: int
    name: str
    position: Literal["GKP", "DEF", "MID", "FWD"]
    club: str  # short name; look up the kit in `clubs`
    price: int
    price_change: int = 0  # this gameweek's price change in tenths (+1 = rose £0.1m)
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
    deadline: datetime | None = None  # the first planned GW's deadline
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


class FeedbackContext(BaseModel):
    page: str = Field("", max_length=40)  # "plans", "plan", "team"
    strategy: str = Field("", max_length=20)
    horizon: int | None = None
    rank: int | None = None  # which plan
    gw: int | None = None


class Feedback(BaseModel):
    """Anonymous feedback from the app. No team IDs or names are sent."""

    kind: Literal["plan", "general"]
    useful: bool | None = None  # thumbs up / down on a plan
    text: str = Field("", max_length=1000)
    context: FeedbackContext = FeedbackContext()


# ---- phase 8: analysis and what-if ----------------------------------------------------------


class ReplacementOut(BaseModel):
    player: int
    gain: float  # projected team points over the horizon vs keeping the player
    weighted_gain: float  # the same, weighted by the strategy (the ranking)


class SpotOut(BaseModel):
    player: int
    level: Literal["red", "amber", "ok"]
    reason: Literal["unavailable", "upgrade"] | None
    gap: float
    replacements: list[ReplacementOut]


class AnalysisResponse(BaseModel):
    entry: int
    strategy: Literal["protect", "balanced", "risky"]
    gws: list[int]
    bank: int
    spots: list[SpotOut]
    players: dict[int, Player]
    clubs: dict[str, Club]


class WhatIfMove(BaseModel):
    gw: int = Field(ge=1, le=38)
    out: int = Field(gt=0)
    into: int = Field(gt=0)


class WhatIfSwap(BaseModel):
    gw: int = Field(ge=1, le=38)
    bench: int = Field(gt=0)  # starter moved to the bench
    start: int = Field(gt=0)  # bench player brought into the XI


class WhatIfRequest(BaseModel):
    team: int = Field(gt=0)
    league: int | None = Field(None, ge=0)
    strategy: Literal["protect", "balanced", "risky"] = "protect"
    horizon: int = Field(4, ge=1, le=5)
    moves: list[WhatIfMove] = Field(default_factory=list, max_length=60)
    captains: dict[int, int] = Field(default_factory=dict)  # gw -> player
    chips: dict[int, ChipName] = Field(default_factory=dict)  # gw -> chip
    swaps: list[WhatIfSwap] = Field(default_factory=list, max_length=60)  # the user's lineup choices


class WhatIfWeek(BaseModel):
    gw: int
    moves: list[Move]
    hits: int
    free_transfers: int  # going into this week
    bank: int  # after this week's moves
    chip: ChipName | None
    squad: list[int]
    starting: list[int]
    bench: list[int]
    captain: int
    vice: int
    xpts: float  # XI + captain (+ chip), minus hits
    best_xi_xpts: float  # the same with the best XI and captain (to show what the user's lineup costs)
    own_lineup: bool  # the user changed the XI this week


class WhatIfProblemOut(BaseModel):
    gw: int | None
    message: str


class WhatIfResponse(BaseModel):
    entry: int
    gws: list[int]
    weeks: list[WhatIfWeek]
    xpts: float  # the whole plan
    no_transfers_xpts: float
    xpts_gain: float
    free_transfers_after: int
    problems: list[WhatIfProblemOut]
    chips_left: list[ChipLeft]


class ReplacementExplainResponse(BaseModel):
    player: int
    status: Literal["ok", "unavailable", "off"]
    why: str | None = None
    watch_out: str | None = None


class WeekMover(BaseModel):
    player: int
    count: int  # managers across FPL who made this move this gameweek


class WeekFlag(BaseModel):
    player: int
    mine: bool  # in the user's squad (otherwise only rivals own him)
    rivals_owned: int
    chance: int | None = None  # % chance of playing next gameweek, when in doubt
    news: str = ""
    yellow_cards: int = 0
    ban_at: int | None = None  # one yellow card from this total, which brings a ban


class TickerGw(BaseModel):
    gw: int
    fixture: str
    difficulty: list[int] = []


class TickerRow(BaseModel):
    club: str
    name: str
    gws: list[TickerGw]
    avg_difficulty: float  # lower = easier run (a blank counts as 5)


class DreamPlayer(BaseModel):
    player: int
    points: int
    mine: bool
    rivals_owned: int


class CaptainOption(BaseModel):
    player: int
    xpts: float  # this gameweek, before doubling
    rivals_captained: int  # rivals who captained him in their last squad
    rivals_owned: int


class LeagueRow(BaseModel):
    entry: int
    name: str
    entry_name: str
    is_me: bool
    rank: int | None
    total: int | None
    xpts: float | None  # projected for the coming gameweek (best XI + captain); None while loading
    projected_total: float | None
    projected_rank: int | None
    captain: int | None  # me: the projected best captain; rivals: who they captained last week
    differentials: list[int] = []  # rivals: their best starters you don't own
    my_differentials: list[int] = []  # rivals: your best starters they don't own
    shared: int | None = None  # players in both squads


class LeagueViewResponse(BaseModel):
    gw: int
    league: LeagueInfo | None
    ready: bool  # rivals' squads are loaded
    rows: list[LeagueRow]  # by current rank
    players: dict[int, Player]
    clubs: dict[str, Club]


class ReviewPlayer(BaseModel):
    player: int
    points: int
    projected: float


class ReviewRival(BaseModel):
    name: str
    entry_name: str
    points: int  # their gameweek points, net of hits
    swing: int  # yours minus theirs: positive = you gained ground


class ReviewResponse(BaseModel):
    gw: int | None
    available: bool
    message: str = ""  # why there's no review yet
    points: int = 0  # your gameweek points, net of hits
    hit_cost: int = 0
    projected: float = 0.0  # what the model projected for your XI and captain before the deadline
    captain: ReviewPlayer | None = None
    best_captain: ReviewPlayer | None = None  # your starter who scored most
    over: list[ReviewPlayer] = []  # starters who beat their projection by most
    under: list[ReviewPlayer] = []
    rivals: list[ReviewRival] = []
    players: dict[int, Player] = {}
    clubs: dict[str, Club] = {}


class WeekResponse(BaseModel):
    gw: int
    deadline: datetime
    last_gw: int | None  # the gameweek the team of the week is from
    n_rivals: int
    rivals_ready: bool
    top_in: list[WeekMover]
    top_out: list[WeekMover]
    flags: list[WeekFlag]
    captains: list[CaptainOption] = []  # your best captain options, best first
    ticker: list[TickerRow]  # easiest run first
    dream_team: list[DreamPlayer]
    players: dict[int, Player]
    clubs: dict[str, Club]


class PlayersResponse(BaseModel):
    """Every player, for the what-if search (projections for the next gameweeks)."""

    gws: list[int]
    players: dict[int, Player]
    clubs: dict[str, Club]
