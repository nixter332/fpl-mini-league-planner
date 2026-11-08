"""Show the facts Claude gets for a plan and, with --call, ask Claude for the reason.

Usage (from backend/):
    python -m scripts.explain --team 5179483 --league 1883627 --offline        # facts only, saved fixtures
    python -m scripts.explain --team 5179483 --league 1883627 --rank 1 --call  # live FPL (cached) + one Claude call

--call uses ANTHROPIC_API_KEY from backend/.env and costs about a cent or two per plan.
Results are cached in data/cache/explanations, so repeating the same plan is free.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.api.service import PlannerService
from app.explain.check import check
from app.explain.explainer import Explainer, facts_text
from app.explain.summary import build_summary
from app.fpl.cache import DiskCache
from app.fpl.client import FPLClient


def offline_service(tmp: Path) -> PlannerService:
    from tests.conftest import load_fixture
    from tests.fakes import FakeFPL, fixture_routes

    manifest = load_fixture("manifest.json")
    when = datetime.fromisoformat(manifest["fetched_at"])
    client = FPLClient(
        DiskCache(tmp, clock=lambda: when.timestamp()),
        transport=httpx.MockTransport(FakeFPL(fixture_routes(manifest))), sleep=lambda _: None, now=lambda: when,
    )
    return PlannerService(client, now=lambda: when)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", type=int, required=True)
    ap.add_argument("--league", type=int, default=None, help="0 = no league")
    ap.add_argument("--strategy", choices=["protect", "balanced", "risky"], default="balanced")
    ap.add_argument("--horizon", type=int, default=4)
    ap.add_argument("--max-hits", type=int, default=1)
    ap.add_argument("--rank", type=int, default=None, help="one plan (1-3); default all")
    ap.add_argument("--offline", action="store_true", help="use the saved fixtures instead of the FPL API")
    ap.add_argument("--call", action="store_true", help="ask Claude (uses your API key)")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # names like João on the Windows console
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    svc = offline_service(Path("data/cache/offline-explain")) if args.offline else PlannerService(FPLClient())
    resp = svc.plans(args.team, args.league, args.strategy, args.horizon, args.max_hits)
    known = svc.known_names()
    explainer = Explainer.from_env() if args.call else None
    if args.call and not explainer.enabled:
        raise SystemExit("No ANTHROPIC_API_KEY found in backend/.env.")

    for plan in resp.plans:
        if args.rank and plan.rank != args.rank:
            continue
        summary = build_summary(resp, plan)
        print(f"\n===== Plan {plan.rank} ({plan.tag}) facts =====")
        print(facts_text(summary))
        if explainer:
            result = asyncio.run(explainer.explain(summary, known))
            print(f"\n----- Plan {plan.rank} reason -----")
            if result is None:
                print("(no reason: failed, refused or rejected by the trust check; see the log above)")
            else:
                print(f"Why: {result.why}\nWatch out: {result.watch_out}")
                assert check(result.why, result.watch_out, facts_text(summary), known) == []


if __name__ == "__main__":
    main()
