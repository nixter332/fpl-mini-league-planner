"""The facts Claude is allowed to use when explaining a plan.

Everything here comes from the optimizer's output (a PlansResponse). Numbers are rounded the
way the app shows them, and anything Claude might want to say ("£0.6m cheaper", "+7.6 before
the hit") is precomputed, so it never has to do arithmetic. The trust check then only accepts
numbers and names that appear in this summary.

Keys contain no digits on purpose: the trust check reads every number in the JSON as allowed.
"""

from typing import Any

from app.api import schemas as s

POSITIONS = {"GKP": "goalkeeper", "DEF": "defender", "MID": "midfielder", "FWD": "forward"}
STRATEGY_MEANING = {
    "protect": "Protect lead: the most expected points, whatever rivals own. For managers who are ahead.",
    "balanced": "Balanced: the most expected points, with a nudge toward players rivals don't have.",
    "risky": "Risky: backs differentials (players rivals don't own) for a bigger swing. For managers who are behind.",
}
PLAN_TYPES = {
    "free": "uses free transfers only",
    "hit": "takes a points hit for extra transfers",
    "roll": "no transfer this week; saves the free transfer",
}
N_THREATS = 3


def r1(x: float) -> float:
    return round(float(x), 1)


def _club_name(resp: s.PlansResponse, short: str) -> str:
    club = resp.clubs.get(short)
    return club.name if club else short


def _opponents(resp: s.PlansResponse, label: str) -> str:
    """'LEE (H), NEW (A)' -> 'Leeds at home, Newcastle away'; '—' -> 'no game'."""
    if label == "—":
        return "no game"
    venues = {"(H)": "at home", "(A)": "away"}
    parts = []
    for part in label.split(", "):
        short, _, venue = part.partition(" ")
        parts.append(f"{_club_name(resp, short)} {venues.get(venue, venue)}".strip())
    return ", ".join(parts)


def _player(resp: s.PlansResponse, pid: int, gws: list[int]) -> dict[str, Any]:
    p = resp.players[pid]
    n = resp.standing.n_rivals if resp.standing else 0
    games = [g for g in p.gws if g.gw in gws]
    card: dict[str, Any] = {
        "name": p.name,
        "club": _club_name(resp, p.club),
        "position": POSITIONS[p.position],
        "games": [{"gameweek": g.gw, "opponent": _opponents(resp, g.fixture), "expected_points": r1(g.xpts)} for g in games],
        "expected_points_total": r1(sum(g.xpts for g in games)),
        "availability": (p.news or "flagged as doubtful") if p.doubtful else "available",
    }
    if n:
        card["rivals_owning"] = f"{p.rivals_owned} of {n}"
    return card


def _transfers(resp: s.PlansResponse, plan: s.Plan) -> list[dict[str, Any]]:
    out = []
    for gw in plan.gameweeks:
        remaining = [g for g in resp.gws if g >= gw.gw]
        for m in gw.moves:
            p_out, p_in = _player(resp, m.player_out, remaining), _player(resp, m.player_in, remaining)
            p_out["sells_for_m"] = r1(m.out_price / 10)
            p_in["costs_m"] = r1(m.in_price / 10)
            diff = m.out_price - m.in_price
            move: dict[str, Any] = {
                "gameweek": gw.gw,
                "out": p_out,
                "in": p_in,
                "expected_points_in_minus_out": r1(p_in["expected_points_total"] - p_out["expected_points_total"]),
            }
            if diff > 0:
                move["money_freed_m"] = r1(diff / 10)
            elif diff < 0:
                move["extra_money_spent_m"] = r1(-diff / 10)
            out.append(move)
    return out


def _xpts(resp: s.PlansResponse, pid: int, gw: int) -> float:
    return next((g.xpts for g in resp.players[pid].gws if g.gw == gw), 0.0)


def _captain(resp: s.PlansResponse, pid: int, gw: int) -> dict[str, Any]:
    out: dict[str, Any] = {"name": resp.players[pid].name, "expected_points": r1(_xpts(resp, pid, gw))}
    if resp.standing and resp.standing.n_rivals:
        out["rivals_who_captained_him_last_week"] = f"{resp.players[pid].rivals_captained} of {resp.standing.n_rivals}"
    return out


def free_transfers_after(plan: s.Plan, max_free: int = 5) -> int:
    """Free transfers left for the gameweek after the plan ends."""
    last = plan.gameweeks[-1]
    return min(last.free_transfers - (len(last.moves) - last.hits) + 1, max_free)


def _gw_label(gws: list[int]) -> str:
    return f"GW{gws[0]}" if len(gws) == 1 else f"GW{gws[0]} to GW{gws[-1]}"


def build_summary(resp: s.PlansResponse, plan: s.Plan) -> dict[str, Any]:
    gws = resp.gws
    first = plan.gameweeks[0]
    name = lambda pid: resp.players[pid].name
    n = resp.standing.n_rivals if resp.standing else 0

    plan_facts: dict[str, Any] = {
        "recommended": plan.rank == 1,
        "type": PLAN_TYPES[plan.tag],
        "expected_points_gain_vs_no_transfers": r1(plan.xpts_gain),
        "transfers": _transfers(resp, plan),
        "captain_this_gameweek": _captain(resp, first.captain, first.gw),
        "this_gameweek_projection": {"you_without_transfers": r1(plan.before.xpts), "you_with_this_plan": r1(plan.after.xpts)},
        "expected_points_gain_this_gameweek": r1(plan.after.xpts - plan.before.xpts),
        "free_transfers_left_after_the_plan": free_transfers_after(plan),
    }
    if plan.hits:
        plan_facts["hits"] = plan.hits
        plan_facts["hit_cost_points"] = 4 * plan.hits
        plan_facts["expected_points_gain_before_hits"] = r1(plan.xpts_gain + 4 * plan.hits)
    if plan.is_roll and len(plan.gameweeks) > 1:
        plan_facts["free_transfers_next_gameweek"] = plan.gameweeks[1].free_transfers
    if n:
        plan_facts["differential_points_gain"] = r1(plan.differential_gain)
        plan_facts["this_gameweek_projection"]["rivals_average"] = r1(plan.after.rivals_avg or 0)
    best = max(plan.after.starting, key=lambda p: _xpts(resp, p, first.gw))
    if best != first.captain and _xpts(resp, best, first.gw) > _xpts(resp, first.captain, first.gw):
        top = _captain(resp, best, first.gw)
        top["expected_points_more_than_your_captain"] = r1(_xpts(resp, best, first.gw) - _xpts(resp, first.captain, first.gw))
        plan_facts["highest_projected_player_in_your_team"] = top
    if not plan.proven_optimal:
        plan_facts["note"] = "the solver ran out of time, so a better plan may exist"

    summary: dict[str, Any] = {
        "strategy": STRATEGY_MEANING[resp.strategy],
        "gameweeks_planned": _gw_label(gws),
        "number_of_gameweeks_planned": len(gws),
        "this_gameweek": f"GW{gws[0]}",
        "free_transfers_now": resp.free_transfers,
        "money_in_bank_m": r1(resp.bank / 10),
        "plan": plan_facts,
        "other_plans": [
            {
                "recommended": o.rank == 1,
                "type": PLAN_TYPES[o.tag],
                "expected_points_gain_vs_no_transfers": r1(o.xpts_gain),
                "expected_points_gain_this_gameweek": r1(o.after.xpts - o.before.xpts),
                "free_transfers_left_after_the_plan": free_transfers_after(o),
                **({"differential_points_gain": r1(o.differential_gain)} if n else {}),
                "transfers_this_gameweek": [f"{name(m.player_out)} out, {name(m.player_in)} in" for m in o.gameweeks[0].moves],
            }
            for o in resp.plans if o.rank != plan.rank
        ],
    }

    if resp.standing:
        st = resp.standing
        league: dict[str, Any] = {"rivals_compared": n}
        if st.rank:
            league["your_rank"] = st.rank
        if st.league.size:
            league["managers_in_league"] = st.league.size
        if st.gap_to_first is not None:
            league["points_behind_first"] = st.gap_to_first
        summary["league"] = league

    threats = plan.threats[:N_THREATS]
    if threats:
        summary["rival_players_you_wont_have"] = [
            {
                "name": name(t.player),
                "club": _club_name(resp, resp.players[t.player].club),
                "rivals_starting_him": f"{t.rivals_starting} of {n}",
                "expected_points_this_gameweek": r1(t.xpts),
            }
            for t in threats
        ]

    h = plan.head_to_head
    if h:
        who = "the league leader" if h.opponent_rank == 1 else "the manager just above you" if h.points_gap > 0 else "your nearest rival"
        summary["head_to_head"] = {
            "opponent": who,
            "opponent_rank": h.opponent_rank,
            "they_lead_by_points": h.points_gap if h.points_gap > 0 else None,
            "you_lead_by_points": -h.points_gap if h.points_gap < 0 else None,
            "your_expected_points_this_gameweek": r1(h.you_xpts),
            "their_expected_points_this_gameweek": r1(h.them_xpts),
            "players_you_share": h.shared_players,
            "your_players_they_lack": [name(p) for p in h.your_differentials],
            "their_players_you_lack": [name(p) for p in h.their_differentials],
            "their_likely_captain": name(h.their_captain),
        }
        summary["head_to_head"] = {k: v for k, v in summary["head_to_head"].items() if v is not None}
    return summary
