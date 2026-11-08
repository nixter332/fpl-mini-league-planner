# Spec: FPL Mini-League Planner v1

The full PRD (problem, users, competitors, metrics) lives in Nikhil's PRD doc. This is the build spec.

## Product in one paragraph

A manager pastes a team link, team ID or mini-league link. The app shows their squad on a pitch with expected points per gameweek, loads their mini-league rivals, and returns the top 3 transfer plans for a strategy they pick: Protect lead, Balanced or Chase. Each plan shows transfers, expected points gained, points gained on rivals, a captain pick, a plain-English reason and the downsides.

## Screens (see `docs/design/`)

Mobile-first web app, dark mode default with a light option. The `.dc.html` files are design references, not production code; read them for layout, copy, colors and interactions.

1. `Main.dc.html`: one input that accepts a team link, a team ID or a league link. A league link shows the member list; tapping your name gives your team ID.
2. `Team.dc.html`: squad on a pitch with club-colour shirts; GW toggle (next 5 GWs) updates fixture, xPts and suggested captain; "xPts / Rivals own" switch; tiles for your projection, rivals' average, edge; bench row.
3. `Plans.dc.html`: strategy dial (3 stops), horizon / max hits / rivals chips, captain card, top 3 plan cards.
4. `PlanDetail.dc.html`: before/after pitch, new player marked IN, rival threats list, head-to-head vs league leader, link to make the transfer in the FPL app.

Design tokens (dark): background `#0B0F14`, surface `#151B23`, raised `#1C2430`, border `#2A3441`, text `#F1F5F9` / `#B4BECB` / `#94A0AF`, accent `#5B3DF5` (links `#A594FF`), good `#4ADE80`, warning/behind `#FB923C`, pitch stripes `#2A7449` / `#266B43`. Fonts: Space Grotesk (headings, numbers), Inter (body).

## Input parsing

Accept and normalize:
- A bare team ID (digits).
- Team links such as `fantasy.premierleague.com/entry/{id}/event/{gw}` or `.../entry/{id}/history`.
- League links such as `fantasy.premierleague.com/leagues/{league_id}/standings/c`.
Anything else → a friendly error that says which formats work.

## FPL endpoints (base `https://fantasy.premierleague.com/api/`)

| Endpoint | Use |
| --- | --- |
| `bootstrap-static/` | Players, teams, prices, ownership, status, xG/xA, gameweeks |
| `fixtures/` | All fixtures with difficulty |
| `event/{gw}/live/` | Every player's stats for one gameweek, in one call (use for history and backtests) |
| `element-summary/{id}/` | One player's history and upcoming fixtures (use sparingly) |
| `entry/{id}/` | Manager info and leagues |
| `entry/{id}/history/` | Per-GW points, transfers made, chips used (derive free transfers) |
| `entry/{id}/transfers/` | Transfer list with prices (derive purchase prices) |
| `entry/{id}/event/{gw}/picks/` | Squad, captain, multipliers for a past GW |
| `leagues-classic/{id}/standings/` | League members and ranks (paginated) |

Field names and pagination must be confirmed against live responses in phase 1; save real responses as test fixtures.

Facts the app must state on screen: squads are as of the last deadline (transfers made since then aren't visible), and rivals' squads are last week's.

## Expected-points model (phase 2)

Per player, per fixture (sum fixtures in a double gameweek; 0 in a blank):

- **Minutes:** probability of starting and of playing 60+, from recent minutes and `chance_of_playing_next_round`.
- **Attack:** goals from xG per 90 and assists from xA per 90, regressed toward the player's longer-run rate, scaled by opponent defensive strength and home/away. Goal points by position, 3 per assist.
- **Clean sheet:** probability from the team's expected goals conceded vs this opponent (e.g. Poisson, P(0 goals)), CS points by position; goals-conceded deductions for GK/DEF.
- **Other:** appearance points, defensive contribution points under the current rules, saves for GKs, a simple bonus estimate.

**Backtest without leakage:** to predict GW k, use only data available before GW k (rebuild from `event/{gw}/live/` for GWs < k, not the current bootstrap totals). Compare mean absolute error per player-GW against FPL's own `ep_next` where available.

**Sanity checks (must pass, as tests):**
- The top-projected premium isn't sold to fund two mid-price players unless the solver's numbers clearly justify it (the v0 Haaland bug).
- A double-gameweek player projects roughly 1.6–2x his single-GW projection.
- Injured (0% chance) players project 0.
- A blank-gameweek player projects 0 for that GW.

## Optimizer (phase 3)

One multi-week MILP over horizon H (default 4 GWs):

- Variables per player p and GW g: in squad, starting, captain, vice, transferred in, transferred out; per GW: free transfers available, hits taken.
- Rules: everything in `docs/v0-lessons.md` → Keep; budget with sell prices; free-transfer rollover; hits capped by the user's max-hits setting; hit buys must start.
- Objective, with strategy weight w (Protect 0, Balanced 0.5, Chase 1) and league effective ownership EO_p:

  maximize Σ_g decay^g · Σ_p xPts[p,g] · (1 − w·EO_p) · (start[p,g] + captain[p,g]) + small bench weight − 4 · hits

- League EO: from rivals' latest picks, EO_p = Σ rivals' multipliers for p ÷ number of rivals (captain counts 2, triple captain 3, bench 0). Use the top 20 rivals by rank, or the ones the user picks.
- **Top 3 plans:** solve, then add a cut that forbids the first plan's GW-1 transfer set and solve again; repeat. Always include "roll the transfer" as a candidate when it's competitive.
- Report per plan: transfers, hits, xPts gained vs no change over H, points gained on rivals, captain per GW.
- Speed: under 5 seconds. Prune the player pool (current squad + top N per position by projected points).

## Explanations (phase 5)

The backend sends the Claude API a structured summary of each plan (players in/out, xPts deltas, fixtures, EO, risks) and asks for a 2–3 sentence reason and a one-line "watch out". The prompt forbids inventing facts or suggesting different players. Cache explanations per plan.

## Phases and gates

1. **Setup and data:** FPL client with caching, link parsing, snapshot script, tests on saved fixtures. Gate: every endpoint above loads, is cached, and has a fixture-based test.
2. **Expected-points model:** build + backtest + sanity checks. Gate: accuracy no worse than `ep_next`; all sanity tests pass.
3. **Optimizer:** points-only, then rival-weighted; top 3 plans. Gate: valid squads every time, under 5 s.
4. **Pitch UI:** Next.js screens from `docs/design/`. Gate: full journey works on Nikhil's own team.
5. **Rivals and explanations:** league import, strategy dial, Claude reasons, downsides. Gate: 3 friends use it before a real deadline.
6. **Launch and learn:** share in mini-leagues, collect feedback each GW, track metrics.
