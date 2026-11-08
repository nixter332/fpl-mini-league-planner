"""Leakage-free backtest: predict each GW k using only live data from GWs < k.

Benchmarks, all computable for past GWs:
- fpl_ep: FPL's ep_next as it would have been just before the GW k deadline. ep_next is
  FPL's `form` x chance of playing (confirmed on the live snapshot: 669/671 players), and
  form is points over GWs whose deadline fell in the last 30 days / the team's fixtures in
  them (671/671). We can't see historical injury news, so chance is taken as 100%, which is
  the same footing as our model in the backtest.
- ppg: season points per team fixture so far.

Error is mean absolute error per player-GW, on players who played in GW k (the main
measure) and on every player whose team had a fixture.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

import pandas as pd

from app.model.history import SeasonData, player_gameweeks
from app.model.project import project

FORM_DAYS = 30


def fpl_form(data: SeasonData, history: pd.DataFrame, at: datetime) -> pd.Series:
    """FPL's `form` at time `at`: points in GWs whose deadline is in (at - 30 days, at],
    divided by the team's fixtures in those GWs, to 1 decimal place."""
    window = [e.id for e in data.bootstrap.events if at - timedelta(days=FORM_DAYS) < e.deadline_time <= at]
    rows = history[history["gw"].isin(window)]
    sums = rows.groupby("element")[["points", "n_fix"]].sum()
    form = (sums["points"] / sums["n_fix"].where(sums["n_fix"] > 0)).fillna(0.0)
    return form.round(1)


def fpl_ep_replica(data: SeasonData, history: pd.DataFrame, gw: int) -> pd.Series:
    """FPL's ep_next for GW `gw` just before its deadline, ignoring injury news."""
    deadline = next(e.deadline_time for e in data.bootstrap.events if e.id == gw)
    return fpl_form(data, history[history["gw"] < gw], deadline - timedelta(seconds=1))


def backtest(data: SeasonData, gws: Iterable[int]) -> pd.DataFrame:
    """One row per GW with sample size and MAE for the model and each benchmark."""
    history = player_gameweeks(data)
    rows = []
    for gw in gws:
        actual = history[history["gw"] == gw].set_index("element")
        past = history[history["gw"] < gw]
        model = project(data, train_through=gw - 1, target_gws=[gw], use_availability=False)
        model = model.xs(gw, level="gw")["xpts"]

        sums = past.groupby("element")[["points", "n_fix"]].sum()
        ppg = (sums["points"] / sums["n_fix"].where(sums["n_fix"] > 0)).fillna(0.0)
        preds = pd.DataFrame(
            {
                "actual": actual["points"],
                "played": actual["minutes"] > 0,
                "had_fixture": actual["n_fix"] > 0,
                "model": model.reindex(actual.index).fillna(0.0),
                "fpl_ep": fpl_ep_replica(data, history, gw).reindex(actual.index).fillna(0.0),
                "ppg": ppg.reindex(actual.index).fillna(0.0),
            }
        )
        for population, mask in (("played", preds["played"]), ("had_fixture", preds["had_fixture"])):
            sub = preds[mask]
            rows.append(
                {
                    "gw": gw,
                    "population": population,
                    "n": len(sub),
                    **{f"mae_{name}": float((sub[name] - sub["actual"]).abs().mean()) for name in ("model", "fpl_ep", "ppg")},
                    "mean_actual": float(sub["actual"].mean()),
                    "mean_model": float(sub["model"].mean()),
                }
            )
    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    """Sample-weighted MAE across GWs, per population."""
    def weighted(group: pd.DataFrame) -> pd.Series:
        w = group["n"]
        cols = [c for c in group.columns if c.startswith("mae_") or c.startswith("mean_")]
        return pd.Series({"n": int(w.sum()), **{c: float((group[c] * w).sum() / w.sum()) for c in cols}})

    return results.groupby("population")[list(results.columns)].apply(weighted)
