# Spec: FPL Mini-League Planner v1

The full PRD (problem, users, competitors, metrics) lives in Nikhil's PRD doc. This is the build spec.

## Product in one paragraph

A manager pastes a team link, team ID or mini-league link. The app shows their squad on a pitch with expected points per gameweek, loads their mini-league rivals, and returns the top 3 transfer plans for a strategy they pick: Protect lead, Balanced or Risky. Each plan shows transfers, expected points gained, differential points gained (points rivals won't also get), a captain pick, a plain-English reason and the downsides.

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
- Objective, with strategy weight w (Protect 0, Balanced 0.15, Risky 0.33) and league ownership split into a starting share S_p and a captaincy share C_p (each a fraction of rivals, 0–1):

  maximize Σ_g decay^g · Σ_p xPts[p,g] · ((1 − w·S_p) · start[p,g] + (1 − w·C_p) · captain[p,g]) + small bench weight − 4 · hits

  *Changed in phase 3 (agreed with Nikhil, 8 Nov 2026):* the original used one EO (up to ~2 with captaincy) and w = 0 / 0.5 / 1, and the strategy was called Chase. That made weights negative, so Chase benched template players like Haaland, and Balanced recommended plans worse than doing nothing. In expectation, rivals' points don't depend on your team, so the dial is a **risk** dial (more differentials, more swing), hence "Risky".
- **Do no harm:** every plan must be expected to score at least as many xPts over the horizon as making no transfers (with the best points-only lineups).
- League ownership: from rivals' latest picks. S_p = share of rivals starting p, C_p = share captaining p; classic EO (captain 2, triple captain 3, bench 0) is kept for display. Use the top 20 rivals by rank, or the ones the user picks.
- **Max hits** is the user's limit on −4 hits over the **whole horizon**, not per gameweek. The UI must say so.
- **Top 3 plans:** solve, then add a cut that forbids the first plan's GW-1 transfer set and solve again; repeat. "Roll the transfer" replaces plan 3 when it's within 1.5 of the best plan's objective.
- Report per plan: transfers (paired like-for-like), hits, xPts gained vs no change over H, differential xPts gained, captain and vice per GW.
- Speed: under 5 seconds. Prune the player pool (current squad + top N per position by projected points). Plans 2–3 run within a time budget and may be the best found rather than proven best (they're still fully validated).

- *Added 9 Nov 2026 (Nikhil):* chips. The planner plays Bench Boost and Triple Captain when a week beats keeping the chip; the user chooses Wildcard and Free Hit weeks, and the app reports what one would add this week. Details: `docs/optimizer.md` → Chips.

## Explanations (phase 5)

The backend sends the Claude API a structured summary of each plan (players in/out, xPts deltas, fixtures, EO, risks) and asks for a 2–3 sentence reason and a one-line "watch out". The prompt forbids inventing facts or suggesting different players. Cache explanations per plan.

## Phases and gates

1. **Setup and data:** FPL client with caching, link parsing, snapshot script, tests on saved fixtures. Gate: every endpoint above loads, is cached, and has a fixture-based test.
2. **Expected-points model:** build + backtest + sanity checks. Gate: accuracy no worse than `ep_next`; all sanity tests pass.
3. **Optimizer:** points-only, then rival-weighted; top 3 plans. Gate: valid squads every time, under 5 s.
4. **Pitch UI:** Next.js screens from `docs/design/`. Gate: full journey works on Nikhil's own team.
5. **Rivals and explanations:** league import, strategy dial, Claude reasons, downsides. Gate: 3 friends use it before a real deadline.
6. **Launch and learn:** share in mini-leagues, collect feedback each GW, track metrics.
   - Saving user data: usage tracking (e.g. PostHog), an in-app feedback button, and a small database.
   - Privacy and sign-in decided here. Never an FPL password (rule 2).
   - Check costs and capacity with more users: the Claude daily cap, Render, and FPL request volume.
   - Gate: agreed with Nikhil when the phase starts.
7. **Chip planner:** for each chip a manager has left, the best gameweeks to play it and why. Examples: "Bench Boost: GW17, your bench has two home games"; "Free Hit: GW15, 5 of your starters blank".
   - The solver ranks the weeks from projections and fixtures (blank and double gameweeks) to the end of each chip's window. Claude explains the ranking.
   - Builds on the GW19 chip backtest, which tunes the chip values first.
   - Gate: chip weeks ranked for Nikhil's squad, with every number traceable to the solver, and a backtest showing the suggestions beat the chip-matched baseline.
8. **Analysis and what-if** (proposed plan: `docs/plans/phase-8.md`):
   - **Analysis:** weak spots on the user's pitch, flagged amber or red by projected points against the best options at the same price and position. Tapping a player shows the best replacements, ranked by the solver, with Claude explaining why.
   - **What-if:** a sandbox where the user makes their own transfers across gameweeks and sees projected points, bank and free transfers update. The backend validates and scores any user-made plan with the same rules as the solver (`validate`, `score`).
   - Gate: a full what-if journey on Nikhil's team with invalid moves blocked and scores matching the solver's.
9. **Drafts** (built 9 Nov 2026 on the device-only version: `frontend/lib/drafts.ts`, `/team/[id]/drafts`): save and compare Wildcard and Free Hit templates. Built on the what-if sandbox.
   - Stored on the device first, then on the server once phase 6 adds storage.
   - Gate: create, edit, compare and delete drafts on a phone.

**Built from the first friends' feedback (10–12 Nov 2026, phase 6).** The phase 5 gate passed: 4 or 5 friends used it before the GW11 deadline.
- Getting in: league invite links (`/?league=<id>`), help finding a link or ID, a sample team for visitors, a "New to FPL?" intro.
- Navigation: a bottom tab bar (My team, Plans, What-if, Rivals, This week); drafts sit under What-if.
- Plans page: one plan open at a time, settings and details folded; preset questions about a plan answered by re-running the optimizer (no LLM).
- Rivals tab: projected league table and what separates you from each rival.
- This week tab: captain options, last gameweek's review, injuries and suspensions, top transfers, fixture ticker, team of the week.
- Also: compare players, deadline calendar file, fixture strips, price changes, deadline countdown, share a plan, home-screen app, error reports.
- Decided against: Google sign-in to fetch leagues (needs an FPL login), price-rise predictions, live points, a free-text chatbot.

*Phases 7–9 added 9 Nov 2026 from Nikhil's review. Also suggested:*
- a 5-week fixture-difficulty strip under each player
- a "before the deadline" screen with this week's 3 actions (transfer, captain, chip) and a countdown

These have no phase yet.
