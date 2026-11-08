# FPL Mini-League Planner

A web app that gives Fantasy Premier League managers transfer plans optimized to beat **their own mini-league rivals**, with a plain-English reason for every move.

Full spec: `docs/SPEC.md`. Lessons from the old prototype: `docs/v0-lessons.md`. Screen designs: `docs/design/`.

## Working with Nikhil

- Nikhil is the PM and reviewer. He decides features; you write the code. Explain what you changed and why in plain language after each task.
- Work in the current phase only (see `docs/SPEC.md` → Phases). Don't start the next phase until its gate passes and Nikhil says go.
- Before a large change, show a short plan and wait for a yes.
- Keep commits small, one logical change each, with clear messages.

## Non-negotiable rules

1. **The solver decides, the AI explains.** Transfers, captain and lineup come only from the optimizer. The Claude API only writes explanations from numbers the solver produced. Never let an LLM pick players.
2. **Never ask for an FPL password or log in to FPL.** Only public endpoints, with team ID and league ID.
3. **No FPL calls from the browser.** All FPL requests go through the backend, cached.
4. **Be polite to the FPL API.** Set a clear User-Agent, throttle bulk calls, cache per gameweek, never fetch per-player data inside a request handler.
5. **No secrets in code or the frontend.** `ANTHROPIC_API_KEY` lives in `backend/.env` (git-ignored).
6. **Tests never hit the live API.** Use saved JSON fixtures in `backend/tests/fixtures/`.

## Stack

- `backend/`: Python 3.11+, FastAPI, httpx, pydantic, pandas/numpy, HiGHS (via `highspy`) or PuLP for the MILP, pytest. Anthropic Python SDK for explanations (phase 5).
- `frontend/`: Next.js (App Router) + TypeScript + Tailwind. Mobile-first, dark mode default. Built in phase 4.
- Hosting: frontend on Vercel (root `frontend`, env `BACKEND_URL`); backend on Render's free tier via `render.yaml`. Steps: `docs/deploy.md`.

## Layout

```
backend/
  app/
    fpl/          # API client, caching, link parsing (team/league IDs)
    model/        # expected-points model + backtest
    optimizer/    # MILP, plans, league effective ownership
    explain/      # Claude API explanations (phase 5)
    api/          # FastAPI routes
  scripts/        # CLI tools (snapshots, backtests)
  tests/
    fixtures/     # saved FPL JSON for tests
  data/cache/     # local cache, git-ignored
frontend/
docs/
```

## Commands

Fill these in as they're created, and keep them current:

- Set up backend: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (Windows: `.venv\Scripts\activate`)
- Run tests: `cd backend && pytest`
- Run API: `cd backend && uvicorn app.api.main:app --reload`
- Refresh test fixtures (calls the live FPL API, ~10-20 throttled requests; finished GWs come from the cache after the first run): `cd backend && python -m scripts.snapshot --team 5179483 --league 1883627`. Tests read `tests/fixtures/manifest.json`, so they follow whatever GW was snapshotted. Update `docs/fpl-api-notes.md` if field names change.
- Backtest the xPts model: `cd backend && python -m scripts.backtest` (offline from fixtures; `--live` uses the cached API; `--from 4 --to 9`). Results and method: `docs/model.md`.
- Injury news archive: `.github/workflows/archive-news.yml` runs `cd backend && python -m scripts.archive_news` every 4 hours and commits `backend/data/news/gw{N}.json` (the news managers saw before each deadline, for fair backtests). Pull before working on that folder.
- Plan backtest (what following the planner each week would have scored; ~150 cached FPL requests the first time, ~10 min): `cd backend && python -m scripts.backtest_plans --leagues 1883627 1863820 1145494 --from 5 --to 9`. Results: `docs/backtest-plans.md`.
- Transfer plans: `cd backend && python -m scripts.plan --team 5179483 --league 1883627 --strategy balanced --horizon 4 --max-hits 0` (`--offline` uses saved fixtures; strategies `protect` / `balanced` / `risky`; max hits is over the whole horizon). Method: `docs/optimizer.md`.
- Plan explanations (Claude): put `ANTHROPIC_API_KEY=...` in `backend/.env`. Preview the facts Claude gets: `cd backend && python -m scripts.explain --team 5179483 --league 1883627 --offline`; add `--call` (and drop `--offline`) for a real, billed Claude call. Method and guardrails: `docs/explanations.md`.
- Run the app locally (two terminals): `cd backend && uvicorn app.api.main:app --port 8000`, then `cd frontend && npm install && npm run dev` and open http://localhost:3000. Next.js proxies `/api/*` to the backend (`BACKEND_URL`, default http://127.0.0.1:8000).
- Frontend checks: `cd frontend && npm run typecheck && npm run build`.
- Screenshot journey (Playwright, phone-sized; starts both servers itself; uses live cached FPL data for team 5179483 / league 1883627): `cd frontend && npx playwright install chromium` once, then `npm run build && npm run screenshots`. Images land in `frontend/e2e/screenshots/` (git-ignored). Claude is switched off in this run (free); `E2E_CLAUDE=1 npx playwright test -g reasons` screenshots real reasons for the Balanced plans (billed the first time, then cached).

## Code style

- Type hints everywhere; pydantic models for FPL responses we depend on.
- FPL prices are integers in tenths of a million (e.g. 95 = £9.5m); keep them as ints internally, format only for display.
- Small, pure functions for model and optimizer logic so they're easy to test.
- Every model or optimizer change gets a test, including the sanity checks in `docs/SPEC.md`.
