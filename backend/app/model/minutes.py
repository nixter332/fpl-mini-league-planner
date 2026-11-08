"""How likely a player is to play, per fixture, from recent minutes.

Only GWs where the player's team had a fixture count. Recent GWs weigh more, and a small
prior (a rarely-used squad player) pulls down players with little history, which is the
"minutes gate" from v0: a player with very few recent minutes is heavily discounted.
"""

from dataclasses import dataclass

import pandas as pd

WINDOW = 6  # team fixtures-GWs to look back
DECAY = 0.8
PRIOR_WEIGHT = 0.3  # tuned on the GW4-9 backtest: lighter is better calibrated, heavier has lower MAE
PRIOR = {"p_appear": 0.2, "p_start": 0.1, "p_60": 0.1, "minutes": 12.0}


@dataclass(frozen=True)
class MinutesProfile:
    """Per-fixture probabilities and expected minutes, assuming the player is available."""

    p_appear: float
    p_start: float
    p_60: float
    minutes: float  # expected minutes per fixture (0 if he doesn't play)


DEFAULT_PROFILE = MinutesProfile(PRIOR["p_appear"], PRIOR["p_start"], PRIOR["p_60"], PRIOR["minutes"])


def minutes_profiles(players: pd.DataFrame) -> dict[int, MinutesProfile]:
    """`players` is the player_gameweeks table already filtered to the training GWs."""
    played = players[players["n_fix"] > 0].sort_values("gw")
    recent = played.groupby("element", sort=False).tail(WINDOW).copy()
    if recent.empty:
        return {}

    recent["age"] = recent.groupby("element")["gw"].rank(ascending=False, method="first") - 1
    recent["w"] = DECAY ** recent["age"]
    n = recent["n_fix"]
    per_fixture = {
        "p_appear": recent["apps"] / n,
        "p_start": recent["starts"].clip(upper=n) / n,
        "p_60": recent["mins60"] / n,
        "minutes": recent["minutes"] / n,
    }

    profiles: dict[int, MinutesProfile] = {}
    w_sum = recent.groupby("element")["w"].sum()
    sums = {k: (v * recent["w"]).groupby(recent["element"]).sum() for k, v in per_fixture.items()}
    for element in w_sum.index:
        den = w_sum[element] + PRIOR_WEIGHT
        values = {k: (sums[k][element] + PRIOR_WEIGHT * PRIOR[k]) / den for k in PRIOR}
        profiles[int(element)] = MinutesProfile(**values)
    return profiles
