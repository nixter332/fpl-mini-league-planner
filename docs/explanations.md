# Plan explanations (phase 5)

Each plan gets a short "Why this plan" (2–3 sentences) and a one-line "Watch out", written by Claude. The optimizer has already chosen the transfers and the captain; Claude only puts its numbers into words.

## How it works

1. `app/explain/summary.py` turns one plan from `/api/plans` into a JSON set of facts. It includes the moves (with prices, fixtures and expected points per gameweek), points gained, differential points, captain, and how many rivals own and captained each player. It also covers the league position, rival threats, the head-to-head and the other plans. Anything Claude might want to say is precomputed (money freed, gain before hits), so it never does arithmetic. Rival managers' names are left out.
2. `app/explain/explainer.py` sends the facts to `claude-opus-5-5` (effort `low`, JSON output with `why` and `watch_out`). The prompt forbids inventing facts and suggesting other players. Refusal fallback is on (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`).
3. `app/explain/check.py` is the trust check:
   - Every number in the text must appear in the facts.
   - No player or club this season may be named unless it's in the facts.
   - Both fields must be filled and short.
   If the check fails, Claude gets one retry with the problems listed. If it fails again, the plan shows no reason.
4. Results, including failures, are cached in `data/cache/explanations/` by a hash of the facts, for 14 days, so the same plan is never paid for twice. API errors aren't cached, so they're retried on the next request.

`GET /api/explain?team&league&strategy&horizon&max_hits&rank` returns `{rank, status, why, watch_out}`. `status` is one of:
- `ok`
- `unavailable`: an error, a refusal or a failed check
- `off`: no `ANTHROPIC_API_KEY`

The frontend asks for each plan's reason separately, so each card fills in as soon as its reason is ready. It hides the box unless the status is `ok`.

## Setup and cost

- Put `ANTHROPIC_API_KEY=...` in `backend/.env` (git-ignored). Real environment variables take precedence over the file. Without a key, everything works except the reasons.
- Each plan costs one call, or two when it's retried. That's about 2–3k input tokens and a few hundred output tokens, roughly 1–2 cents at Opus 5.5 prices. Repeat views are free.
- Tests use a fake client (`tests/fakes.py: FakeClaude`). `tests/conftest.py` blanks the key, so tests can never call Claude.

## Changing the prompt or the facts

Bump `PROMPT_VERSION` in `explainer.py` so old cached text isn't reused. Keep fact keys free of digits: the trust check treats every number in the facts JSON as allowed. A test enforces this.
