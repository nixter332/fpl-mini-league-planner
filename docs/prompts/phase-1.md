# Phase 1 prompt for Claude Code

Paste this into Claude Code after opening the project folder:

---

Read CLAUDE.md, docs/SPEC.md and docs/v0-lessons.md. We're starting phase 1 (setup and data) only.

Goal: a Python backend data layer for the FPL API that later phases can build on.

Build:
1. The backend skeleton from the layout in CLAUDE.md, with requirements.txt, .gitignore (include .venv, .env, data/cache) and a minimal FastAPI app with a /health route.
2. `app/fpl/client.py`: an httpx client for every endpoint in docs/SPEC.md, with a clear User-Agent, timeouts, retries with backoff, and throttling for bulk calls.
3. `app/fpl/cache.py`: a disk cache under data/cache/. Shared data (bootstrap, fixtures, event live) is cached per gameweek; manager and league data expires after a short time. Read from the cache first.
4. `app/fpl/links.py`: parse a bare team ID, team links and league links into {type, id}, per docs/SPEC.md → Input parsing, with clear errors.
5. Pydantic models only for the fields we'll actually use; tolerate extra fields.
6. `scripts/snapshot.py`: given a team ID and a league ID, fetch everything for the current gameweek and save the raw JSON under backend/tests/fixtures/. Confirm the real field names (e.g. purchase prices in picks, the defensive contribution field, standings pagination) and write what you find into docs/fpl-api-notes.md.
7. Tests with pytest that use only the saved fixtures: link parsing, cache hit/miss, model parsing, next-actionable-gameweek logic.

Before writing code, show me a short plan and the file list, and wait for my OK. When done, tell me how to run the tests and the snapshot script, and stop. Don't start phase 2.

My team ID: [YOUR TEAM ID]
A league ID to test with: [YOUR LEAGUE ID]
