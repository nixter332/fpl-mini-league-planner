"""Builds API responses from the FPL client, the xPts model and the optimizer.

Season-wide work (live history, projections) is done once and kept in memory for a few
minutes; computed plan sets are kept too, so switching screens is instant. Every FPL request
still goes through the cached, throttled client.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from app.api import schemas as s
from app.api.kits import GOALKEEPER, kit_for
from app.fpl.client import FPLClient, FPLNotFound
from app.fpl.gameweeks import latest_finished_gameweek, latest_started_gameweek, next_actionable_gameweek
from app.fpl.links import parse_link
from app.fpl.models import Bootstrap, Element, Entry, EntryPicks, Event, EventLive, Fixture, LeagueStandings, Team
from app.model.history import SeasonData
from app.model.project import project
from app.model.scoring import GKP, POSITION_CODES
from app.optimizer.inputs import build_pool, load_state
from app.optimizer.lineup import Lineup, best_lineup
from app.optimizer.ownership import NO_RIVALS, LeagueOwnership, league_ownership
from app.optimizer.plans import Plan as OptPlan
from app.optimizer.chips import (
    AUTO_CHIPS, BENCH_BOOST, CHIP_LABELS, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD, ChipWindow, window_for,
)
from app.optimizer.analysis import analyse
from app.optimizer.plans import make_plans, paired_transfers
from app.optimizer.solver import PoolPlayer
from app.optimizer.whatif import Move as WhatIfMove
from app.optimizer.whatif import build_plan, week_points
from app.optimizer.solver import Settings
from app.optimizer.state import SquadState

log = logging.getLogger(__name__)

TEAM_VIEW_GWS = 5
CONTEXT_TTL = 10 * 60  # older than this: answer from it, refresh in the background
CONTEXT_MAX_AGE = 60 * 60  # older than this (or past a deadline): rebuild before answering
PLAN_CACHE_SIZE = 32
N_RIVALS = 20
DOUBT_STATUSES = {"d", "i", "s", "u"}


def _private_leagues(entry: Entry) -> list[s.LeagueInfo]:
    """The user's private classic leagues, smallest first (the likeliest mini-league)."""
    private = [l for l in entry.leagues.classic if l.league_type == "x"]
    private.sort(key=lambda l: (l.rank_count is None, l.rank_count or 0, l.id))
    return [s.LeagueInfo(id=l.id, name=l.name, size=l.rank_count) for l in private]


class NotFoundError(LookupError):
    """Something the user asked for doesn't exist (message is safe to show)."""


class InvalidRequestError(ValueError):
    """The request can't be planned as asked, e.g. a chip that's already used (safe to show)."""


def _chips_left(chips: tuple[ChipWindow, ...]) -> list[s.ChipLeft]:
    return [s.ChipLeft(name=c.name, label=CHIP_LABELS[c.name], start=c.start, stop=c.stop) for c in chips]


@dataclass(frozen=True)
class SeasonContext:
    data: SeasonData
    now: datetime
    finished_gw: int
    gws: tuple[int, ...]  # the next actionable GW and the ones after it
    events: dict[int, Event]
    xpts: dict[int, dict[int, float]]  # element -> gw -> xPts
    projection: pd.DataFrame
    elements: dict[int, Element]
    teams: dict[int, Team]
    fixture_labels: dict[tuple[int, int], str]
    built_at: float


@dataclass(frozen=True)
class LeagueBundle:
    standing: s.Standing
    ownership: LeagueOwnership
    rival_picks: dict[int, EntryPicks]  # empty while the rivals are still loading
    rows: list  # StandingRow, sorted by rank
    progress: s.RivalsProgress


class PlannerService:
    def __init__(self, client: FPLClient, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.client = client
        self._now = now
        self._lock = threading.Lock()
        self._build_lock = threading.Lock()  # one season build at a time
        self._refreshing = False
        self._context: SeasonContext | None = None
        self._plans: OrderedDict[tuple, s.PlansResponse] = OrderedDict()
        # Rivals' picks are fetched in the background, one league at a time, through the same
        # throttled client, so the team screen can show while they load.
        self._prefetcher = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rivals")
        self._jobs: dict[int, Future] = {}

    # ---- season-wide data ------------------------------------------------------------------

    def context(self) -> SeasonContext:
        """Season-wide data. A fresh copy is built at most every CONTEXT_TTL; until then (and up to
        CONTEXT_MAX_AGE) requests are answered from the current copy while a new one is built in the
        background, so nobody waits for a rebuild. Past a deadline it's rebuilt first, so plans
        never target a gameweek that has already started."""
        ctx = self._context
        if ctx is None or self._must_rebuild(ctx):
            with self._build_lock:
                ctx = self._context
                if ctx is None or self._must_rebuild(ctx):
                    ctx = self._context = self._build_context()
            return ctx
        if time.monotonic() - ctx.built_at > CONTEXT_TTL:
            self._refresh_in_background()
        return ctx

    def _must_rebuild(self, ctx: SeasonContext) -> bool:
        if time.monotonic() - ctx.built_at > CONTEXT_MAX_AGE:
            return True
        deadline = ctx.events[ctx.gws[0]].deadline_time
        return deadline <= self._now()

    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def run() -> None:
            try:
                with self._build_lock:
                    self._context = self._build_context()
            except Exception as e:  # keep serving the old copy; the next request tries again
                log.warning("Background season refresh failed: %s", e)
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=run, name="season-refresh", daemon=True).start()

    def warm_up(self) -> None:
        """Build the season data now (call in a background thread at start-up)."""
        try:
            self.context()
        except Exception as e:
            log.warning("Warm-up failed (the first request will try again): %s", e)

    def _build_context(self) -> SeasonContext:
        now = self._now()
        bootstrap = Bootstrap.model_validate(self.client.bootstrap())
        finished = latest_finished_gameweek(bootstrap.events)
        finished_gw = finished.id if finished else 0
        actionable = next_actionable_gameweek(bootstrap.events, now)
        if actionable is None:
            raise NotFoundError("The season's last deadline has passed. See you next season!")
        gws = tuple(g for g in range(actionable.id, actionable.id + TEAM_VIEW_GWS) if g <= len(bootstrap.events))
        live = {gw: EventLive.model_validate(self.client.event_live(gw)) for gw in range(1, finished_gw + 1)}
        fixtures = [Fixture.model_validate(f) for f in self.client.fixtures()]
        data = SeasonData(bootstrap, fixtures, live)

        projection = project(data, train_through=finished_gw, target_gws=gws)
        xpts: dict[int, dict[int, float]] = {}
        for (element, gw), value in projection["xpts"].items():
            xpts.setdefault(int(element), {})[int(gw)] = round(float(value), 2)

        teams = {t.id: t for t in bootstrap.teams}
        labels: dict[tuple[int, int], list[str]] = {}
        for f in sorted(fixtures, key=lambda f: (f.kickoff_time is None, f.kickoff_time)):
            if f.event in gws:
                labels.setdefault((f.team_h, f.event), []).append(f"{teams[f.team_a].short_name} (H)")
                labels.setdefault((f.team_a, f.event), []).append(f"{teams[f.team_h].short_name} (A)")
        return SeasonContext(
            data=data, now=now, finished_gw=finished_gw, gws=gws,
            events={e.id: e for e in bootstrap.events}, xpts=xpts, projection=projection,
            elements={e.id: e for e in bootstrap.elements}, teams=teams,
            fixture_labels={k: ", ".join(v) for k, v in labels.items()},
            built_at=time.monotonic(),
        )

    # ---- resolve ---------------------------------------------------------------------------

    def resolve(self, raw: str) -> s.ResolveResponse:
        link = parse_link(raw)  # LinkParseError -> 400
        if link.type == "number":
            # A bare number can be a team ID or a league ID (often both exist): look up both.
            entry = self._maybe(lambda: Entry.model_validate(self.client.entry(link.id)))
            page = self._maybe(lambda: LeagueStandings.model_validate(self.client.league_standings(link.id)))
            if entry and page:
                return s.ResolveResponse(
                    type="choice", id=link.id, team_name=entry.name,
                    manager_name=f"{entry.player_first_name} {entry.player_last_name}", league_name=page.league.name,
                    members=self._members(page), more_members=page.standings.has_next,
                )
            if page:
                return self._league_response(link.id, page)
            if not entry:
                raise FPLNotFound(f"No team or league {link.id}")
            return self._team_response(entry)
        if link.type == "team":
            return self._team_response(Entry.model_validate(self.client.entry(link.id)))  # 404 if it doesn't exist
        return self._league_response(link.id, LeagueStandings.model_validate(self.client.league_standings(link.id)))

    @staticmethod
    def _maybe(fetch: Callable[[], object]):
        try:
            return fetch()
        except FPLNotFound:
            return None

    @staticmethod
    def _members(page: LeagueStandings) -> list[s.Member]:
        return [
            s.Member(entry=r.entry, player_name=r.player_name, entry_name=r.entry_name, rank=r.rank, total=r.total)
            for r in page.standings.results
        ]

    def _team_response(self, entry: Entry) -> s.ResolveResponse:
        league_id = self._pick_league(None, _private_leagues(entry))
        if league_id:
            self._submit(league_id, lambda: self._prefetch(league_id, entry.id))
        return s.ResolveResponse(type="team", id=entry.id)

    def _league_response(self, league_id: int, page: LeagueStandings) -> s.ResolveResponse:
        # Start loading rivals while the user finds themselves in the list.
        self._submit(league_id, lambda: self._prefetch(league_id, None))
        return s.ResolveResponse(
            type="league", id=league_id, league_name=page.league.name, members=self._members(page),
            more_members=page.standings.has_next,
        )

    # ---- team screen -----------------------------------------------------------------------

    def team(self, entry_id: int, league_id: int | None, wait_rivals: bool = False) -> s.TeamResponse:
        """With wait_rivals=False, rivals not yet loaded are fetched in the background and the
        response says how far along that is (`rivals`); ask again when it's ready."""
        ctx = self.context()
        entry = Entry.model_validate(self.client.entry(entry_id))
        state = load_state(self.client, entry_id, ctx.data.bootstrap, ctx.now)
        leagues = _private_leagues(entry)
        league_id = self._pick_league(league_id, leagues)
        bundle = self._league(league_id, entry, state.picks_gw, wait=wait_rivals) if league_id else None
        ownership = bundle.ownership if bundle else NO_RIVALS

        lineups = []
        for gw in ctx.gws:
            lineup = self._lineup(state.element_ids, gw, ctx)
            rivals_avg = self._rivals_avg(bundle, gw, ctx) if bundle else None
            lineups.append(self._lineup_gw(gw, lineup, rivals_avg))

        squad = sorted(state.element_ids, key=lambda p: (ctx.elements[p].element_type, p))
        return s.TeamResponse(
            entry=entry_id,
            team_name=entry.name,
            manager_name=f"{entry.player_first_name} {entry.player_last_name}",
            picks_gw=state.picks_gw,
            free_transfers=state.free_transfers,
            bank=state.bank,
            leagues=leagues,
            standing=bundle.standing if bundle else None,
            rivals=bundle.progress if bundle else None,
            gameweeks=[s.Gameweek(id=g, name=ctx.events[g].name, deadline=ctx.events[g].deadline_time) for g in ctx.gws],
            lineups=lineups,
            squad=squad,
            players=self._players(squad, ctx, ownership, state),
            clubs=self._clubs(ctx),
            facts=self._facts(state, bundle),
            chips_left=_chips_left(state.chips),
        )

    # ---- plans -----------------------------------------------------------------------------

    def plans(
        self, entry_id: int, league_id: int | None, strategy: str, horizon: int, max_hits: int,
        *, wildcard: int | None = None, freehit: int | None = None, chips: bool = True,
    ) -> s.PlansResponse:
        """wildcard / freehit: the GW the user chose to play that chip in. chips: whether the
        planner may play Bench Boost and Triple Captain when they're worth it."""
        ctx = self.context()
        horizon = max(1, min(horizon, len(ctx.gws)))
        key = (entry_id, league_id, strategy, horizon, max_hits, wildcard, freehit, chips, ctx.built_at)
        with self._lock:
            if key in self._plans:
                self._plans.move_to_end(key)
                return self._plans[key]

        entry = Entry.model_validate(self.client.entry(entry_id))
        leagues = _private_leagues(entry)
        league_id = self._pick_league(league_id, leagues)
        state = load_state(self.client, entry_id, ctx.data.bootstrap, ctx.now)
        bundle = self._league(league_id, entry, state.picks_gw) if league_id else None
        ownership = bundle.ownership if bundle else NO_RIVALS

        gws = ctx.gws[:horizon]
        forced = []
        for name, gw in ((WILDCARD, wildcard), (FREE_HIT, freehit)):
            if gw is None:
                continue
            if gw not in gws:
                raise InvalidRequestError(f"GW{gw} isn't in this plan (GW{gws[0]} to GW{gws[-1]}).")
            if window_for(state.chips, name, gw) is None:
                raise InvalidRequestError(f"You don't have a {CHIP_LABELS[name]} to play in GW{gw}.")
            forced.append((gw, name))
        if wildcard is not None and wildcard == freehit:
            raise InvalidRequestError("Only one chip can be played per gameweek.")
        settings = Settings(
            gws, strategy=strategy, max_hits=max_hits, chips=state.chips,
            auto_chips=AUTO_CHIPS if chips else frozenset(), forced_chips=tuple(forced),
        )
        pool = build_pool(ctx.data.bootstrap, ctx.projection, state, gws)
        plan_set = make_plans(pool, state, settings, ownership)
        g0 = gws[0]
        rivals_avg = self._rivals_avg(bundle, g0, ctx) if bundle else None
        before = self._lineup_gw(g0, self._lineup(state.element_ids, g0, ctx), rivals_avg)

        sell = {p.element: p.sell_price for p in state.players}
        pool_by_id = {p.element: p for p in pool}
        plans = [self._plan(p, ctx, state, bundle, before, rivals_avg, sell, pool_by_id, horizon) for p in plan_set.plans]

        referenced = set(state.element_ids)
        for plan in plans:
            for gw in plan.gameweeks:
                referenced.update(m.player_in for m in gw.moves)
            referenced.update(t.player for t in plan.threats)
            if plan.head_to_head:
                referenced.update(plan.head_to_head.their_differentials)
                referenced.add(plan.head_to_head.their_captain)

        response = s.PlansResponse(
            entry=entry_id, strategy=strategy, horizon=horizon, max_hits=max_hits, gws=list(gws),
            chips_left=_chips_left(state.chips), wildcard_gw=wildcard, freehit_gw=freehit, auto_chips=chips,
            free_transfers=state.free_transfers, bank=state.bank,
            standing=bundle.standing if bundle else None,
            captain_note=self._captain_note(plans[0], ctx, ownership) if plans else "",
            plans=plans,
            players=self._players(referenced, ctx, ownership, state),
            clubs=self._clubs(ctx),
            facts=self._facts(state, bundle),
            seconds=round(plan_set.seconds, 2),
        )
        with self._lock:
            self._plans[key] = response
            while len(self._plans) > PLAN_CACHE_SIZE:
                self._plans.popitem(last=False)
        return response

    def _plan(self, plan: OptPlan, ctx, state, bundle, before, rivals_avg, sell, pool_by_id, horizon) -> s.Plan:
        sol = plan.solution
        first = sol.first
        gws = []
        for gw in sol.gameweeks:
            moves = [
                s.Move(player_out=o, player_in=i, out_price=sell.get(o, pool_by_id[o].sell_price), in_price=pool_by_id[i].buy_price)
                for o, i in paired_transfers(gw, pool_by_id)
            ]
            chip_x = self._chip_xpts(gw, ctx)
            gws.append(s.PlanGw(gw=gw.gw, moves=moves, hits=gw.hits, free_transfers=gw.free_transfers,
                                bank=gw.bank, captain=gw.captain, vice=gw.vice,
                                chip=gw.chip, chip_xpts=round(chip_x, 2) if gw.chip else None))
            if gw.chip != FREE_HIT:
                for o, i in paired_transfers(gw, pool_by_id):
                    sell[i] = pool_by_id[i].buy_price  # bought in the plan: sells for what was paid
        g0 = first.gw
        chip_total = sum(g.chip_xpts or 0.0 for g in gws)
        after_xpts = (sum(ctx.xpts.get(p, {}).get(g0, 0.0) for p in first.starting) + ctx.xpts.get(first.captain, {}).get(g0, 0.0)
                      + self._chip_xpts(first, ctx))
        after = s.LineupGw(
            gw=g0, starting=list(first.starting), bench=list(first.bench), captain=first.captain, vice=first.vice,
            xpts=round(after_xpts, 2), rivals_avg=rivals_avg,
            edge=round(after_xpts - rivals_avg, 2) if rivals_avg is not None else None,
        )
        tag = "roll" if plan.is_roll else ("hit" if first.hits else "free")
        if plan.is_roll:
            next_ft = sol.gameweeks[1].free_transfers if len(sol.gameweeks) > 1 else None
            summary = "No transfer this week." + (f" Save it: {next_ft} free transfers in GW{sol.gameweeks[1].gw}." if next_ft else "")
        else:
            summary = f"{plan.xpts_gain:+.1f} xPts over {horizon} GW{'s' if horizon > 1 else ''} vs making no transfers"
            summary += f", after {4 * plan.hits} pts of hits." if plan.hits else "."
        last = gws[-1]
        ft_after = last.free_transfers if last.chip in (WILDCARD, FREE_HIT) else min(last.free_transfers - (len(last.moves) - last.hits) + 1, 5)
        if not plan.is_roll:
            summary += f" Leaves {ft_after} free transfer{'s' if ft_after != 1 else ''} for GW{last.gw + 1}."
        chip_weeks = [g for g in gws if g.chip]
        if chip_weeks:
            summary += " Chips: " + ", ".join(
                f"{CHIP_LABELS[g.chip]} in GW{g.gw}" + (f" (+{g.chip_xpts:.1f})" if g.chip in (BENCH_BOOST, TRIPLE_CAPTAIN) else "")
                for g in chip_weeks
            ) + "."
        return s.Plan(
            rank=plan.rank, tag=tag, is_roll=plan.is_roll, proven_optimal=sol.proven_optimal, hits=plan.hits,
            xpts=round(plan.xpts, 2), xpts_gain=round(plan.xpts_gain, 2), chip_xpts=round(chip_total, 2),
            differential_gain=round(plan.differential_gain, 2),
            summary=summary, gameweeks=gws, before=before, after=after,
            threats=self._threats(set(first.squad), g0, ctx, bundle) if bundle else [],
            head_to_head=self._head_to_head(first, g0, ctx, bundle, after_xpts) if bundle else None,
        )

    @staticmethod
    def _chip_xpts(gw, ctx: SeasonContext) -> float:
        """Expected points a Bench Boost or Triple Captain adds that week (0 otherwise)."""
        x = lambda p: ctx.xpts.get(p, {}).get(gw.gw, 0.0)
        if gw.chip == BENCH_BOOST:
            return sum(x(p) for p in gw.bench)
        if gw.chip == TRIPLE_CAPTAIN:
            return x(gw.captain)
        return 0.0

    def chip_advice(self, entry_id: int, league_id: int | None, strategy: str, horizon: int, max_hits: int, chips: bool = True) -> list[s.ChipAdvice]:
        """For each Wildcard / Free Hit the user could play this week: the best plan with it,
        compared with the best plan without it. Facts from the optimizer, not a recommendation;
        a Wildcard's value beyond the horizon isn't counted."""
        base = self.plans(entry_id, league_id, strategy, horizon, max_hits, chips=chips)
        if not base.plans:
            return []
        g0 = base.gws[0]
        best = base.plans[0].xpts_gain
        out = []
        for c in base.chips_left:
            if c.name not in (WILDCARD, FREE_HIT) or not c.start <= g0 <= c.stop:
                continue
            kw = {"wildcard": g0} if c.name == WILDCARD else {"freehit": g0}
            with_chip = self.plans(entry_id, league_id, strategy, horizon, max_hits, chips=chips, **kw)
            if with_chip.plans:
                gain = with_chip.plans[0].xpts_gain
                out.append(s.ChipAdvice(chip=c.name, label=c.label, gw=g0, xpts_gain=round(gain, 2), vs_best_plan=round(gain - best, 2)))
        return out

    def plan(
        self, entry_id: int, league_id: int | None, strategy: str, horizon: int, max_hits: int, rank: int,
        *, wildcard: int | None = None, freehit: int | None = None, chips: bool = True,
    ) -> tuple[s.PlansResponse, s.Plan]:
        resp = self.plans(entry_id, league_id, strategy, horizon, max_hits, wildcard=wildcard, freehit=freehit, chips=chips)
        plan = next((p for p in resp.plans if p.rank == rank), None)
        if plan is None:
            raise NotFoundError("That plan isn't available any more.")
        return resp, plan

    # ---- phase 8: analysis and what-if -----------------------------------------------------

    def _every_player(self, ctx: SeasonContext, state: SquadState, gws) -> dict[int, PoolPlayer]:
        """A PoolPlayer for every player (owned ones at their selling price)."""
        sell = {p.element: p.sell_price for p in state.players}
        return {
            e.id: PoolPlayer(e.id, e.element_type, e.team, e.now_cost, sell.get(e.id, e.now_cost),
                             {g: ctx.xpts.get(e.id, {}).get(g, 0.0) for g in gws})
            for e in ctx.elements.values()
        }

    def _buyable(self, ctx: SeasonContext) -> set[int]:
        return {e.id for e in ctx.elements.values() if e.status != "u" and e.can_transact}

    def _setup(self, entry_id: int, league_id: int | None, horizon: int):
        ctx = self.context()
        entry = Entry.model_validate(self.client.entry(entry_id))
        league_id = self._pick_league(league_id, _private_leagues(entry))
        state = load_state(self.client, entry_id, ctx.data.bootstrap, ctx.now)
        bundle = self._league(league_id, entry, state.picks_gw) if league_id else None
        gws = ctx.gws[:max(1, min(horizon, len(ctx.gws)))]
        return ctx, state, bundle, gws

    def analysis(self, entry_id: int, league_id: int | None, strategy: str, horizon: int) -> s.AnalysisResponse:
        ctx, state, bundle, gws = self._setup(entry_id, league_id, horizon)
        ownership = bundle.ownership if bundle else NO_RIVALS
        players = self._every_player(ctx, state, gws)
        availability = {}
        for e in ctx.elements.values():
            chance = e.chance_of_playing_next_round
            availability[e.id] = (chance if chance is not None else (0 if e.status in {"i", "s", "u"} else 100)) / 100
        spots = analyse(state, players, self._buyable(ctx), gws, availability, ownership, Settings(gws, strategy=strategy).weight)
        referenced = set(state.element_ids) | {r.element for sp in spots for r in sp.replacements}
        return s.AnalysisResponse(
            entry=entry_id, strategy=strategy, gws=list(gws), bank=state.bank,
            spots=[
                s.SpotOut(player=sp.element, level=sp.level, reason=sp.reason, gap=sp.gap,
                          replacements=[s.ReplacementOut(player=r.element, gain=r.gain, weighted_gain=r.weighted_gain) for r in sp.replacements])
                for sp in spots
            ],
            players=self._players(referenced, ctx, ownership, state),
            clubs=self._clubs(ctx),
        )

    def what_if(self, req: s.WhatIfRequest) -> s.WhatIfResponse:
        ctx, state, bundle, gws = self._setup(req.team, req.league, req.horizon)
        players = self._every_player(ctx, state, gws)
        names = {e.id: e.web_name for e in ctx.elements.values()}
        settings = Settings(gws, strategy=req.strategy, chips=state.chips)
        moves = [WhatIfMove(m.gw, m.out, m.into) for m in req.moves]
        sol, problems = build_plan(state, players, names, settings, moves, req.captains, req.chips)
        base, _ = build_plan(state, players, names, settings)
        sell = {p.element: p.sell_price for p in state.players}
        weeks = []
        for gw in sol.gameweeks:
            pairs = paired_transfers(gw, players)
            weeks.append(s.WhatIfWeek(
                gw=gw.gw, hits=gw.hits, free_transfers=gw.free_transfers, bank=gw.bank, chip=gw.chip,
                moves=[s.Move(player_out=o, player_in=i, out_price=sell.get(o, players[o].sell_price), in_price=players[i].buy_price) for o, i in pairs],
                squad=list(gw.squad), starting=list(gw.starting), bench=list(gw.bench), captain=gw.captain, vice=gw.vice,
                xpts=round(week_points(gw, players), 2),
            ))
            if gw.chip != FREE_HIT:
                for o, i in pairs:
                    sell[i] = players[i].buy_price
        total = sum(w.xpts for w in weeks)
        base_total = sum(week_points(g, players) for g in base.gameweeks)
        last = sol.gameweeks[-1]
        ft_after = last.free_transfers if last.chip in (WILDCARD, FREE_HIT) else min(last.free_transfers - (len(last.transfers_in) - last.hits) + 1, 5)
        return s.WhatIfResponse(
            entry=req.team, gws=list(gws), weeks=weeks, xpts=round(total, 2), no_transfers_xpts=round(base_total, 2),
            xpts_gain=round(total - base_total, 2), free_transfers_after=ft_after,
            problems=[s.WhatIfProblemOut(gw=p.gw, message=p.message) for p in problems],
            chips_left=_chips_left(state.chips),
        )

    def all_players(self, entry_id: int, league_id: int | None) -> s.PlayersResponse:
        """Every player with projections and rivals' ownership (if loaded), for the what-if search."""
        ctx = self.context()
        entry = Entry.model_validate(self.client.entry(entry_id))
        league_id = self._pick_league(league_id, _private_leagues(entry))
        state = load_state(self.client, entry_id, ctx.data.bootstrap, ctx.now)
        bundle = self._league(league_id, entry, state.picks_gw, wait=False) if league_id else None
        ownership = bundle.ownership if bundle else NO_RIVALS
        ids = self._buyable(ctx) | set(state.element_ids)
        return s.PlayersResponse(gws=list(ctx.gws), players=self._players(ids, ctx, ownership, state), clubs=self._clubs(ctx))

    def known_names(self) -> frozenset[str]:
        """Every player and club name this season, for the explanation trust check."""
        ctx = self.context()
        names = {e.web_name for e in ctx.elements.values()}
        names |= {t.name for t in ctx.teams.values()} | {t.short_name for t in ctx.teams.values()}
        return frozenset(names)

    # ---- helpers ---------------------------------------------------------------------------

    @staticmethod
    def _pick_league(league_id: int | None, leagues: list[s.LeagueInfo]) -> int | None:
        """None -> the first league in the list (the smallest private league, most likely the
        user's mini-league); 0 -> no league (points only)."""
        if league_id == 0:
            return None
        if league_id is None:
            return leagues[0].id if leagues else None
        return league_id

    # ---- rivals ----------------------------------------------------------------------------

    def _standings(self, league_id: int) -> tuple[LeagueStandings, list]:
        page = LeagueStandings.model_validate(self.client.league_standings(league_id))
        rows = sorted(page.standings.results, key=lambda r: r.rank)
        if not rows:
            raise NotFoundError("That league has no managers yet.")
        return page, rows

    @staticmethod
    def _rival_ids(rows: list, entry_id: int | None) -> list[int]:
        """The top N on page 1, excluding the user. Without a user yet, one extra so the set
        covers whoever it turns out to be."""
        ids = [r.entry for r in rows if r.entry != entry_id]
        return ids[:N_RIVALS + (1 if entry_id is None else 0)]

    def _job(self, league_id: int) -> Future | None:
        with self._lock:
            return self._jobs.get(league_id)

    def _submit(self, league_id: int, fn: Callable[[], object]) -> None:
        """Run a background fetch for this league unless one is already running."""
        with self._lock:
            job = self._jobs.get(league_id)
            if job is not None and not job.done():
                return
            job = self._prefetcher.submit(fn)
            self._jobs[league_id] = job

        def report(f: Future) -> None:
            if f.exception() is not None:
                log.warning("Rival prefetch for league %s failed: %s", league_id, f.exception())

        job.add_done_callback(report)

    def _prefetch(self, league_id: int, entry_id: int | None) -> None:
        bootstrap = Bootstrap.model_validate(self.client.bootstrap())
        started = latest_started_gameweek(bootstrap.events, self._now())
        if started is None:
            return
        _, rows = self._standings(league_id)
        self.client.many_entry_picks(self._rival_ids(rows, entry_id), started.id)

    def rivals_progress(self, entry_id: int, league_id: int | None) -> s.RivalsProgress:
        """How many rivals' squads are loaded; starts loading them if needed."""
        entry = Entry.model_validate(self.client.entry(entry_id))
        league_id = self._pick_league(league_id, _private_leagues(entry))
        if not league_id:
            return s.RivalsProgress(league_id=0, loaded=0, total=0, ready=True)
        ctx = self.context()
        state = load_state(self.client, entry_id, ctx.data.bootstrap, ctx.now)
        return self._league(league_id, entry, state.picks_gw, wait=False).progress

    def _league(self, league_id: int, entry: Entry, gw: int, wait: bool = True) -> LeagueBundle:
        """Rivals are the top N on page 1 of the standings (50 per page), so even huge leagues
        cost one request. The user's own rank and total come from their entry.

        With wait=False and some rivals not cached yet, their picks load in the background and
        the bundle has none (progress.ready is False). A finished background fetch counts as
        ready even if a rival has no picks for this GW (joined late)."""
        page, rows = self._standings(league_id)
        rivals = self._rival_ids(rows, entry.id)
        loaded = sum(self.client.has_picks(r, gw) for r in rivals)
        job = self._job(league_id)
        job_finished = job is not None and job.done()
        if not wait and loaded < len(rivals) and not job_finished:
            self._submit(league_id, lambda: self.client.many_entry_picks(rivals, gw))
            picks: dict[int, EntryPicks] = {}
            progress = s.RivalsProgress(league_id=league_id, loaded=loaded, total=len(rivals), ready=False)
        else:
            if job is not None and not job.done():  # let it finish rather than fetch twice
                try:
                    job.result(timeout=120)
                except Exception:  # the fetch below retries and reports properly
                    pass
            raw = self.client.many_entry_picks(rivals, gw)  # throttled bulk fetch, cached
            picks = {r: EntryPicks.model_validate(v) for r, v in raw.items() if v is not None}
            progress = s.RivalsProgress(league_id=league_id, loaded=len(rivals), total=len(rivals), ready=True)
        mine = next((l for l in entry.leagues.classic if l.id == league_id), None)
        my_row = next((r for r in rows if r.entry == entry.id), None)
        rank = my_row.rank if my_row else (mine.entry_rank if mine else None)
        total = my_row.total if my_row else entry.summary_overall_points
        leader = rows[0]
        standing = s.Standing(
            league=s.LeagueInfo(id=league_id, name=page.league.name, size=mine.rank_count if mine else None),
            rank=rank, total=total,
            leader_name=leader.player_name, leader_entry_name=leader.entry_name,
            gap_to_first=(leader.total - total) if total is not None else None,
            n_rivals=len(picks) if progress.ready else len(rivals),
        )
        return LeagueBundle(standing, league_ownership(picks.values()), picks, rows, progress)

    def _lineup(self, squad, gw: int, ctx: SeasonContext) -> Lineup:
        position = {p: ctx.elements[p].element_type for p in squad}
        return best_lineup(squad, position, {p: ctx.xpts.get(p, {}).get(gw, 0.0) for p in squad})

    def _rivals_avg(self, bundle: LeagueBundle, gw: int, ctx: SeasonContext) -> float | None:
        if not bundle.rival_picks:
            return None
        totals = [self._lineup([p.element for p in pk.picks], gw, ctx).xpts for pk in bundle.rival_picks.values()]
        return round(sum(totals) / len(totals), 2)

    @staticmethod
    def _lineup_gw(gw: int, lineup: Lineup, rivals_avg: float | None) -> s.LineupGw:
        return s.LineupGw(
            gw=gw, starting=list(lineup.starting), bench=list(lineup.bench), captain=lineup.captain, vice=lineup.vice,
            xpts=round(lineup.xpts, 2), rivals_avg=rivals_avg,
            edge=round(lineup.xpts - rivals_avg, 2) if rivals_avg is not None else None,
        )

    def _threats(self, squad: set[int], gw: int, ctx: SeasonContext, bundle: LeagueBundle) -> list[s.Threat]:
        own = bundle.ownership
        candidates = [p for p in own.start if p not in squad]
        ranked = sorted(candidates, key=lambda p: -own.start_share(p) * ctx.xpts.get(p, {}).get(gw, 0.0))
        return [
            s.Threat(player=p, rivals_starting=round(own.start_share(p) * own.n_rivals), xpts=ctx.xpts.get(p, {}).get(gw, 0.0))
            for p in ranked[:5] if ctx.xpts.get(p, {}).get(gw, 0.0) > 0
        ]

    def _head_to_head(self, first, gw: int, ctx: SeasonContext, bundle: LeagueBundle, you_xpts: float) -> s.HeadToHead | None:
        me = bundle.standing
        target = next((r for r in bundle.rows if r.entry in bundle.rival_picks and (me.rank is None or r.rank < me.rank)), None)
        target = target or next((r for r in bundle.rows if r.entry in bundle.rival_picks), None)
        if target is None:
            return None
        their_squad = [p.element for p in bundle.rival_picks[target.entry].picks]
        theirs = self._lineup(their_squad, gw, ctx)
        mine = set(first.squad)
        x = lambda p: ctx.xpts.get(p, {}).get(gw, 0.0)
        return s.HeadToHead(
            opponent_name=target.player_name, opponent_entry_name=target.entry_name, opponent_rank=target.rank,
            points_gap=(target.total - me.total) if me.total is not None else 0,
            you_xpts=round(you_xpts, 2), them_xpts=round(theirs.xpts, 2),
            shared_players=len(mine & set(their_squad)),
            your_differentials=sorted((p for p in first.starting if p not in their_squad), key=lambda p: -x(p))[:3],
            their_differentials=sorted((p for p in theirs.starting if p not in mine), key=lambda p: -x(p))[:3],
            their_captain=theirs.captain,
        )

    def _captain_note(self, plan: s.Plan, ctx: SeasonContext, ownership: LeagueOwnership) -> str:
        g0 = plan.after.gw
        cap = plan.after.captain
        name = ctx.elements[cap].web_name
        x = ctx.xpts.get(cap, {}).get(g0, 0.0)
        top = max(plan.after.starting, key=lambda p: ctx.xpts.get(p, {}).get(g0, 0.0))
        note = f"{name}: {x:.1f} xPts in GW{g0}"
        note += ", the highest in your XI." if top == cap else f" ({ctx.elements[top].web_name} projects {ctx.xpts[top][g0]:.1f})."
        if ownership.n_rivals:
            k = round(ownership.captain_share(cap) * ownership.n_rivals)
            note += f" {k} of {ownership.n_rivals} rivals captained him last week."
        return note

    def _players(self, ids, ctx: SeasonContext, ownership: LeagueOwnership, state: SquadState) -> dict[int, s.Player]:
        sell = {p.element: p.sell_price for p in state.players}
        out = {}
        for pid in ids:
            e = ctx.elements[pid]
            out[pid] = s.Player(
                id=pid, name=e.web_name, position=POSITION_CODES[e.element_type], club=ctx.teams[e.team].short_name,
                price=e.now_cost, sell_price=sell.get(pid), status=e.status, news=e.news,
                doubtful=e.status in DOUBT_STATUSES or (e.chance_of_playing_next_round not in (None, 100)),
                rivals_owned=ownership.owned.get(pid, 0),
                rivals_captained=round(ownership.captain_share(pid) * ownership.n_rivals),
                gws=[s.PlayerGw(gw=g, fixture=ctx.fixture_labels.get((e.team, g), "—"), xpts=ctx.xpts.get(pid, {}).get(g, 0.0)) for g in ctx.gws],
            )
        return out

    @staticmethod
    def _clubs(ctx: SeasonContext) -> dict[str, s.Club]:
        clubs = {t.short_name: s.Club(id=t.id, short_name=t.short_name, name=t.name, kit=kit_for(t.short_name)) for t in ctx.teams.values()}
        clubs["GKP"] = s.Club(id=0, short_name="GKP", name="Goalkeeper", kit=GOALKEEPER)
        return clubs

    @staticmethod
    def _facts(state: SquadState, bundle: LeagueBundle | None) -> list[str]:
        facts = [f"Your squad is as of the GW{state.picks_gw} deadline. Transfers you've made since then aren't visible."]
        if bundle:
            facts.append(f"Rivals' squads are from GW{state.picks_gw}, so last week's.")
        return facts
