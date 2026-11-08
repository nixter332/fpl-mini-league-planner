"""FPL scoring rules, read from bootstrap's game_config so rule changes flow through.

A few thresholds aren't in the API and are constants here (confirmed from live data
or the official rules; see docs/fpl-api-notes.md).
"""

from dataclasses import dataclass
from typing import Any

GKP, DEF, MID, FWD = 1, 2, 3, 4
POSITION_CODES = {GKP: "GKP", DEF: "DEF", MID: "MID", FWD: "FWD"}

LONG_PLAY_MINUTES = 60
SAVES_PER_POINT = 3
GOALS_CONCEDED_PER_POINT = 2
# Defensive actions needed for the DC bonus (DEF: CBI + tackles; MID/FWD: + recoveries).
DC_THRESHOLDS = {GKP: None, DEF: 10, MID: 12, FWD: 12}


@dataclass(frozen=True)
class ScoringRules:
    short_play: int
    long_play: int
    assists: int
    saves: int
    yellow_cards: int
    goals_scored: dict[int, int]
    clean_sheets: dict[int, int]
    goals_conceded: dict[int, int]
    defensive_contribution: dict[int, int]

    @classmethod
    def from_game_config(cls, scoring: dict[str, Any]) -> "ScoringRules":
        def by_position(key: str) -> dict[int, int]:
            values = scoring[key]
            return {pos: int(values[code]) for pos, code in POSITION_CODES.items()}

        dc = by_position("defensive_contribution")
        dc = {pos: (pts if DC_THRESHOLDS[pos] is not None else 0) for pos, pts in dc.items()}
        return cls(
            short_play=int(scoring["short_play"]),
            long_play=int(scoring["long_play"]),
            assists=int(scoring["assists"]),
            saves=int(scoring["saves"]),
            yellow_cards=int(scoring["yellow_cards"]),
            goals_scored=by_position("goals_scored"),
            clean_sheets=by_position("clean_sheets"),
            goals_conceded=by_position("goals_conceded"),
            defensive_contribution=dc,
        )
