"""FastAPI app. The frontend calls these routes; the browser never talks to FPL directly."""

from collections.abc import Callable
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.api import schemas as s
from app.api.service import NotFoundError, PlannerService
from app.fpl.client import FPLClient, FPLError, FPLNotFound
from app.fpl.links import LinkParseError

app = FastAPI(title="FPL Mini-League Planner")
_service: PlannerService | None = None


def get_service() -> PlannerService:
    global _service
    if _service is None:
        _service = PlannerService(FPLClient())
    return _service


def set_service(service: PlannerService | None) -> None:
    """For tests: swap in a service backed by saved fixtures."""
    global _service
    _service = service


@app.exception_handler(LinkParseError)
def _bad_link(_: Request, exc: LinkParseError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(FPLNotFound)
def _fpl_not_found(_: Request, exc: FPLNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "We couldn't find that team or league on FPL. Check the ID or link."})


@app.exception_handler(NotFoundError)
def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(FPLError)
def _fpl_down(_: Request, exc: FPLError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "FPL isn't responding right now (it may be updating). Try again in a few minutes."})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/resolve", response_model=s.ResolveResponse)
def resolve(input: str = Query(..., min_length=1, max_length=300), svc: PlannerService = Depends(get_service)) -> s.ResolveResponse:
    return svc.resolve(input)


@app.get("/api/team/{entry_id}", response_model=s.TeamResponse)
def team(entry_id: int, league: int | None = Query(None, ge=0, description="0 = no league"), svc: PlannerService = Depends(get_service)) -> s.TeamResponse:
    return svc.team(entry_id, league)


@app.get("/api/plans", response_model=s.PlansResponse)
def plans(
    team: int = Query(..., gt=0),
    league: int | None = Query(None, ge=0, description="0 = no league"),
    strategy: Literal["protect", "balanced", "risky"] = "balanced",
    horizon: int = Query(4, ge=1, le=5),
    max_hits: int = Query(1, ge=0, le=4, description="Most -4 hits over the whole horizon"),
    svc: PlannerService = Depends(get_service),
) -> s.PlansResponse:
    if horizon < 1:
        raise HTTPException(400, "Horizon must be at least 1 gameweek.")
    return svc.plans(team, league, strategy, horizon, max_hits)
