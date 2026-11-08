"""Pydantic models for the FPL fields we depend on. Extra fields are ignored.

FPL sends many decimals as strings ("0.45"); pydantic converts them to float.
Prices stay as ints in tenths of a million (62 = £6.2m). Field notes: docs/fpl-api-notes.md.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FPLModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---- bootstrap-static -------------------------------------------------------------------


class Event(FPLModel):
    id: int
    name: str
    deadline_time: datetime
    finished: bool
    data_checked: bool
    is_current: bool
    is_next: bool
    is_previous: bool


class Team(FPLModel):
    id: int
    code: int  # used for shirt images
    name: str
    short_name: str
    # In 2026/27 `strength` is null and the attack/defence strengths are all 0, so they're
    # not modelled. Derive team strength from fixture results instead (phase 2).
    strength_overall_home: int  # 1-5
    strength_overall_away: int  # 1-5


class ElementType(FPLModel):
    id: int  # 1 GKP, 2 DEF, 3 MID, 4 FWD
    singular_name_short: str
    squad_select: int  # how many of this position in a 15-man squad
    squad_min_play: int
    squad_max_play: int


class Element(FPLModel):
    """A player as listed in bootstrap-static (season totals so far)."""

    id: int
    web_name: str
    first_name: str
    second_name: str
    team: int
    element_type: int
    now_cost: int
    cost_change_start: int
    can_transact: bool
    status: str  # a available, d doubtful, i injured, s suspended, u unavailable
    chance_of_playing_next_round: int | None
    chance_of_playing_this_round: int | None = None
    news: str
    news_added: datetime | None
    selected_by_percent: float
    ep_next: float | None
    form: float
    total_points: int
    minutes: int
    starts: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    saves: int
    bonus: int
    bps: int
    expected_goals: float
    expected_assists: float
    expected_goals_conceded: float
    expected_goals_per_90: float
    expected_assists_per_90: float
    # Count of defensive actions (CBI + tackles, plus recoveries for MID/FWD), not points.
    defensive_contribution: int
    defensive_contribution_per_90: float

    @property
    def start_cost(self) -> int:
        """Price at the start of the season (purchase price for players held since GW1)."""
        return self.now_cost - self.cost_change_start


class GameRules(FPLModel):
    squad_squadsize: int
    squad_squadplay: int
    squad_team_limit: int
    squad_total_spend: int
    transfers_sell_on_fee: float
    max_extra_free_transfers: int
    element_sell_at_purchase_price: bool


class GameConfig(FPLModel):
    rules: GameRules
    scoring: dict[str, Any]


class ChipDef(FPLModel):
    """One chip and the gameweeks it can be played in (each chip comes twice a season)."""

    id: int
    name: str  # wildcard, freehit, bboost, 3xc
    number: int
    start_event: int
    stop_event: int
    chip_type: str


class Bootstrap(FPLModel):
    events: list[Event]
    teams: list[Team]
    element_types: list[ElementType]
    elements: list[Element]
    game_config: GameConfig
    chips: list[ChipDef] = []


# ---- fixtures/ --------------------------------------------------------------------------


class Fixture(FPLModel):
    id: int
    event: int | None  # None = not yet scheduled
    kickoff_time: datetime | None
    team_h: int
    team_a: int
    team_h_difficulty: int
    team_a_difficulty: int
    started: bool | None
    finished: bool
    finished_provisional: bool
    team_h_score: int | None
    team_a_score: int | None


# ---- event/{gw}/live/ -------------------------------------------------------------------


class LiveStats(FPLModel):
    minutes: int
    starts: int
    total_points: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    saves: int
    bonus: int
    bps: int
    yellow_cards: int
    defensive_contribution: int
    expected_goals: float
    expected_assists: float
    expected_goals_conceded: float


class ExplainStat(FPLModel):
    identifier: str
    points: int
    value: int


class ExplainFixture(FPLModel):
    """Points breakdown for one fixture (two entries in a double gameweek)."""

    fixture: int
    stats: list[ExplainStat]


class LiveElement(FPLModel):
    id: int
    stats: LiveStats
    explain: list[ExplainFixture]


class EventLive(FPLModel):
    elements: list[LiveElement]


# ---- element-summary/{id}/ --------------------------------------------------------------


class SummaryFixture(FPLModel):
    id: int
    event: int | None
    team_h: int
    team_a: int
    is_home: bool
    difficulty: int
    kickoff_time: datetime | None


class SummaryHistory(FPLModel):
    """One past fixture for one player. `value` is the player's price at that time."""

    round: int
    fixture: int
    opponent_team: int
    was_home: bool
    minutes: int
    total_points: int
    value: int
    expected_goals: float
    expected_assists: float
    defensive_contribution: int


class ElementSummary(FPLModel):
    fixtures: list[SummaryFixture]
    history: list[SummaryHistory]


# ---- entry/{id}/ ------------------------------------------------------------------------


class EntryClassicLeague(FPLModel):
    id: int
    name: str
    league_type: str  # "x" private, "s" system (overall, country, club)
    entry_rank: int | None
    rank_count: int | None = None  # number of managers in the league


class EntryLeagues(FPLModel):
    classic: list[EntryClassicLeague]


class Entry(FPLModel):
    id: int
    name: str
    player_first_name: str
    player_last_name: str
    started_event: int
    current_event: int | None
    last_deadline_bank: int | None
    last_deadline_value: int | None
    last_deadline_total_transfers: int | None
    summary_overall_points: int | None
    summary_overall_rank: int | None
    leagues: EntryLeagues


# ---- entry/{id}/history/ ----------------------------------------------------------------


class HistoryEvent(FPLModel):
    event: int
    points: int
    total_points: int
    overall_rank: int | None
    bank: int
    value: int
    # Wildcard and free-hit weeks report 0 here even though transfers were made.
    event_transfers: int
    event_transfers_cost: int
    points_on_bench: int


class ChipPlay(FPLModel):
    name: str  # wildcard, freehit, bboost, 3xc
    event: int


class EntryHistory(FPLModel):
    current: list[HistoryEvent]
    chips: list[ChipPlay]


# ---- entry/{id}/transfers/ --------------------------------------------------------------


class Transfer(FPLModel):
    element_in: int
    element_in_cost: int  # the purchase price we need for sell values
    element_out: int
    element_out_cost: int
    event: int
    time: datetime


# ---- entry/{id}/event/{gw}/picks/ -------------------------------------------------------


class Pick(FPLModel):
    element: int
    position: int  # 1-11 starting, 12-15 bench in order
    multiplier: int  # 0 bench, 1 starter, 2 captain, 3 triple captain
    is_captain: bool
    is_vice_captain: bool


class EntryPicks(FPLModel):
    active_chip: str | None
    picks: list[Pick]
    entry_history: HistoryEvent


# ---- leagues-classic/{id}/standings/ ----------------------------------------------------


class StandingRow(FPLModel):
    entry: int
    entry_name: str
    player_name: str
    rank: int
    last_rank: int
    total: int
    event_total: int


class StandingsPage(FPLModel):
    has_next: bool
    page: int
    results: list[StandingRow]


class League(FPLModel):
    id: int
    name: str


class LeagueStandings(FPLModel):
    league: League
    standings: StandingsPage
    new_entries: dict[str, Any] = Field(default_factory=dict)
