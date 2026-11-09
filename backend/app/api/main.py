"""FastAPI app. The frontend calls these routes; the browser never talks to FPL directly."""

import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api import schemas as s
from app.api.limits import RateLimiter, client_key
from app.api.service import InvalidRequestError, NotFoundError, PlannerService
from app.explain.explainer import Explainer
from app.explain.summary import build_summary
from app.fpl.client import FPLClient, FPLError, FPLNotFound
from app.fpl.links import LinkParseError

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # ANTHROPIC_API_KEY; real env vars win

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the season's data as soon as the server starts, so the first visitor after a deploy
    doesn't wait for it. WARM_UP=0 switches this off (tests)."""
    if os.environ.get("WARM_UP", "1") == "1":
        threading.Thread(target=lambda: get_service().warm_up(), name="warm-up", daemon=True).start()
    yield


app = FastAPI(title="FPL Mini-League Planner", lifespan=lifespan)
_service: PlannerService | None = None
_explainer: Explainer | None = None

FEEDBACK_PER_HOUR = 20  # per visitor
EXPLAIN_PER_HOUR = 60  # per visitor; a plans page asks for 3
PLANS_PER_HOUR = 120  # per visitor; each plan set is a few seconds of CPU
explain_limiter = RateLimiter(EXPLAIN_PER_HOUR, 3600)
feedback_limiter = RateLimiter(FEEDBACK_PER_HOUR, 3600)
feedback_log = logging.getLogger("feedback")
plans_limiter = RateLimiter(PLANS_PER_HOUR, 3600)


def get_service() -> PlannerService:
    global _service
    if _service is None:
        _service = PlannerService(FPLClient())
    return _service


def set_service(service: PlannerService | None) -> None:
    """For tests: swap in a service backed by saved fixtures."""
    global _service
    _service = service


def get_explainer() -> Explainer:
    global _explainer
    if _explainer is None:
        _explainer = Explainer.from_env()
    return _explainer


def set_explainer(explainer: Explainer | None) -> None:
    """For tests: swap in an explainer with a fake Claude client."""
    global _explainer
    _explainer = explainer


@app.exception_handler(LinkParseError)
def _bad_link(_: Request, exc: LinkParseError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(FPLNotFound)
def _fpl_not_found(_: Request, exc: FPLNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "We couldn't find that team or league on FPL. Check the ID or link."})


@app.exception_handler(NotFoundError)
def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidRequestError)
def _invalid(_: Request, exc: InvalidRequestError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(FPLError)
def _fpl_down(_: Request, exc: FPLError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "FPL isn't responding right now (it may be updating). Try again in a few minutes."})


@app.get("/health")
@app.get("/api/health")  # through the frontend proxy: the start page pings it to wake a sleeping server
def health() -> dict[str, str]:
    """`version` is the deployed commit (Render sets RENDER_GIT_COMMIT), so a deploy can be verified."""
    return {"status": "ok", "version": os.environ.get("RENDER_GIT_COMMIT", "local")[:7]}


@app.get("/api/resolve", response_model=s.ResolveResponse)
def resolve(input: str = Query(..., min_length=1, max_length=300), svc: PlannerService = Depends(get_service)) -> s.ResolveResponse:
    return svc.resolve(input)


@app.get("/api/team/{entry_id}", response_model=s.TeamResponse)
def team(
    entry_id: int,
    league: int | None = Query(None, ge=0, description="0 = no league"),
    wait_rivals: bool = Query(False, description="false: answer now and load rivals in the background"),
    svc: PlannerService = Depends(get_service),
) -> s.TeamResponse:
    return svc.team(entry_id, league, wait_rivals)


@app.get("/api/rivals", response_model=s.RivalsProgress)
def rivals(
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0, description="0 = no league"),
    svc: PlannerService = Depends(get_service),
) -> s.RivalsProgress:
    """How many rivals' squads are loaded (and start loading them). Poll until ready."""
    return svc.rivals_progress(team, league)


@app.get("/api/plans", response_model=s.PlansResponse)
def plans(
    request: Request,
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0, description="0 = no league"),
    strategy: Literal["protect", "balanced", "risky"] = "balanced",
    horizon: int = Query(4, ge=1, le=5),
    max_hits: int = Query(0, ge=0, le=4, description="Most -4 hits over the whole horizon"),
    wildcard: int | None = Query(None, ge=1, le=38, description="Play your Wildcard in this GW"),
    freehit: int | None = Query(None, ge=1, le=38, description="Play your Free Hit in this GW"),
    chips: bool = Query(True, description="Let the planner play Bench Boost / Triple Captain when worth it"),
    svc: PlannerService = Depends(get_service),
) -> s.PlansResponse:
    if horizon < 1:
        raise HTTPException(400, "Horizon must be at least 1 gameweek.")
    if not plans_limiter.allow(client_key(request)):
        raise HTTPException(429, "You've built a lot of plans in the last hour. Try again in a bit.")
    return svc.plans(team, league, strategy, horizon, max_hits, wildcard=wildcard, freehit=freehit, chips=chips)


@app.get("/api/chip-advice", response_model=list[s.ChipAdvice])
def chip_advice(
    request: Request,
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0, description="0 = no league"),
    strategy: Literal["protect", "balanced", "risky"] = "balanced",
    horizon: int = Query(4, ge=1, le=5),
    max_hits: int = Query(0, ge=0, le=4),
    chips: bool = Query(True),
    svc: PlannerService = Depends(get_service),
) -> list[s.ChipAdvice]:
    """What a Wildcard / Free Hit this week would add over the best plan without it."""
    if not plans_limiter.allow(client_key(request)):
        raise HTTPException(429, "You've built a lot of plans in the last hour. Try again in a bit.")
    return svc.chip_advice(team, league, strategy, horizon, max_hits, chips)


@app.get("/api/explain", response_model=s.ExplainResponse)
async def explain(
    request: Request,
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0, description="0 = no league"),
    strategy: Literal["protect", "balanced", "risky"] = "balanced",
    horizon: int = Query(4, ge=1, le=5),
    max_hits: int = Query(0, ge=0, le=4),
    wildcard: int | None = Query(None, ge=1, le=38),
    freehit: int | None = Query(None, ge=1, le=38),
    chips: bool = Query(True),
    rank: int = Query(..., ge=1, le=3),
    svc: PlannerService = Depends(get_service),
    explainer: Explainer = Depends(get_explainer),
) -> s.ExplainResponse:
    """A Claude-written reason for one plan. The plan itself comes from the (cached) optimizer run."""
    if not explainer.enabled:
        return s.ExplainResponse(rank=rank, status="off")
    if not explain_limiter.allow(client_key(request)):
        return s.ExplainResponse(rank=rank, status="unavailable")  # the plan still shows, without a reason
    resp, plan = await run_in_threadpool(
        lambda: svc.plan(team, league, strategy, horizon, max_hits, rank, wildcard=wildcard, freehit=freehit, chips=chips)
    )
    known = await run_in_threadpool(svc.known_names)
    result = await explainer.explain(build_summary(resp, plan), known)
    if result is None:
        return s.ExplainResponse(rank=rank, status="unavailable")
    return s.ExplainResponse(rank=rank, status="ok", why=result.why, watch_out=result.watch_out)


analysis_limiter = RateLimiter(240, 3600)  # cheap, but each call scores ~200 lineups
what_if_limiter = RateLimiter(600, 3600)  # one call per change in the sandbox


@app.get("/api/analysis", response_model=s.AnalysisResponse)
def analysis(
    request: Request,
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0, description="0 = no league"),
    strategy: Literal["protect", "balanced", "risky"] = "protect",
    horizon: int = Query(4, ge=1, le=5),
    svc: PlannerService = Depends(get_service),
) -> s.AnalysisResponse:
    """Weak spots in the squad and the best legal replacements for each player."""
    if not analysis_limiter.allow(client_key(request)):
        raise HTTPException(429, "That's a lot of analysis in an hour. Try again in a bit.")
    return svc.analysis(team, league, strategy, horizon)


@app.post("/api/what-if", response_model=s.WhatIfResponse)
def what_if(body: s.WhatIfRequest, request: Request, svc: PlannerService = Depends(get_service)) -> s.WhatIfResponse:
    """Score the user's own transfers (and captains, chips) with the planner's rules and points."""
    if not what_if_limiter.allow(client_key(request)):
        raise HTTPException(429, "That's a lot of changes in an hour. Try again in a bit.")
    return svc.what_if(body)


@app.get("/api/players", response_model=s.PlayersResponse)
def players(
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0),
    svc: PlannerService = Depends(get_service),
) -> s.PlayersResponse:
    """Every player with projections, for the what-if player search."""
    return svc.all_players(team, league)


@app.post("/api/feedback")
def feedback(body: s.Feedback, request: Request) -> dict[str, bool]:
    """Logged as one JSON line (Render keeps the logs; no database yet, see docs/SPEC.md phase 6)."""
    if not feedback_limiter.allow(client_key(request)):
        raise HTTPException(429, "Thanks! That's plenty of feedback for now.")
    feedback_log.warning("FEEDBACK %s", json.dumps(body.model_dump(), ensure_ascii=False))
    return {"ok": True}
