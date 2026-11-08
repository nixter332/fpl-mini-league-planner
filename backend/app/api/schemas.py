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
    type: Literal["team", "league"]
    id: int
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


class TeamResponse(BaseModel):
    entry: int
    team_name: str
    manager_name: str
    picks_gw: int
    free_transfers: int
    bank: int
    leagues: list[LeagueInfo]  # private classic leagues, for the switcher
    standing: Standing | None
    gameweeks: list[Gameweek]
    lineups: list[LineupGw]
    squad: list[int]
    players: dict[int, Player]
    clubs: dict[str, Club]
    facts: list[str]


class Move(BaseModel):
    player_out: int
    player_in: int
    out_price: int  # what selling raises
    in_price: int


class PlanGw(BaseModel):
    gw: int
    moves: list[Move]
    hits: int
    free_transfers: int
    bank: int
    captain: int
    vice: int


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
    xpts_gain: float
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
