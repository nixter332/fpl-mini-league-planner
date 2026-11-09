# Phase 8 plan: analysis and what-if

**Status:** proposal for Nikhil's approval (9 Nov 2026). This won't be built before the phase 5 gate passes and Nikhil says go.

## Goal

Two things the transfer plans don't do today:
- show *where* a squad is weak
- let a manager try their own transfers and see what they'd do

The rules stay the same: the solver ranks every option, Claude only explains, and no player is ever chosen by the AI.

## 1. Analysis on the team screen

**What you see.** The team screen gets a **Show weak spots** toggle next to "xPts / Rivals own". When it's on, each player on the pitch gets a coloured ring:
- **Red:** a clear upgrade exists, or he's injured or suspended for most of the next weeks.
- **Amber:** a modest upgrade exists.
- **No ring:** he's fine for now.

**How a weak spot is scored.** For each player, compare his projected points over the plan horizon (default 4 GWs) with the best single replacement the manager could actually make. That means:
- same position
- price at most his selling price plus the bank
- the 3-per-club rule still holds

The colour comes from the gap: red at 6+ points over 4 GWs (or availability under 50%), amber at 3–6. Bench players count only for the weeks they'd be likely to come on. These thresholds are a starting point, and the plan backtest can check them, the same way as hits.

**Tapping a player** opens a sheet with:
- his next 4 fixtures with projected points, and his injury news
- the **top 3 replacements**, ranked by points gained over the horizon. In Balanced and Risky this also weighs how many rivals own them, the same weighting as the planner. Each shows price, fixtures, projected points and how many rivals own him.
- a short reason for the top option, written by Claude from those numbers and covered by the same trust check as plan reasons
- a **Try in what-if** button

**How it's computed.** Ranking single swaps is simple enumeration, with no solver run, so it takes milliseconds:
- for each owned player, each affordable same-position player not already owned
- score = projected points gained over the horizon, plus the strategy's differential weight

New endpoint: `GET /api/analysis?team&league&strategy&horizon` → per-player gap and colour, plus the top 3 replacements. It's cached with the season data.

## 2. What-if sandbox

**What you see.** A new screen, `/team/[id]/what-if`, opened from the team screen or from "Try in what-if":
- gameweek tabs (GW11…GW14) and the pitch, as on the team screen
- tap a player, then **Transfer out**; pick a replacement from a searchable list filtered to his position and what's affordable, sorted by projected points
- after each change, these update:
  - **this week:** projected points, bank and free transfers, plus hits (−4 each beyond free transfers)
  - **the whole plan:** total points, compared with "no transfers" and with the planner's Plan 1
- transfers in a later week apply on top of earlier ones, as in FPL
- you can set the captain (the default is the top projection), play a chip in a week, and undo or reset
- illegal moves are blocked as you make them, with a plain reason ("Only 3 players per club", "£0.4m short"). These are the same rules the planner obeys.

**How it's computed.** New endpoint, `POST /api/what-if`, which takes the user's moves per GW (and optional captains and chips) and returns:
- per GW: squad, best XI, captain, projected points, bank, free transfers and hits
- the totals
- any rule violations

It reuses the solver's own rule checker (`validate`) and points scorer (`score`, `best_lineup`), so its numbers match the planner's exactly.

## 3. What Claude explains

Two short texts, both from numbers only and both behind the trust check:
- **Analysis:** why the top replacement is the best swap.
- **What-if (optional, on request):** "your plan compared with Plan 1" in two sentences, such as "you gain 2.1 in GW11 but give up 4.5 by GW14 because…".

## Build order (small commits)

1. Backend: `/api/what-if` with the shared rule checker and scorer, plus tests (it must match the planner exactly).
2. Backend: `/api/analysis` with replacement ranking, plus tests (sanity: never suggests an unaffordable or same-club-overflow swap).
3. Frontend: the weak-spots toggle and the player sheet.
4. Frontend: the what-if screen.
5. Claude reasons for replacements and the what-if comparison.
6. Phone journey tests, live check, docs.

## Gate (from the spec)

A full what-if journey on Nikhil's team, on a phone:
- invalid moves are blocked
- every number matches the solver's (a test replays Plan 1 in what-if and gets the same points)
- weak spots and replacements make sense to Nikhil

## Decisions for Nikhil

1. **Thresholds:** red at 6+ points over 4 GWs and amber at 3–6, as a start. OK?
2. **Rivals in replacements:** follow the chosen strategy (Protect = points only)? *Recommended: yes.*
3. **Chips in what-if:** include them from the start, or add later? *Recommended: include. The rules are already built.*
4. **Saving what-if plans:** that's phase 9 (drafts). Until then, a what-if lives in the page address, so it can be bookmarked or shared as a link. OK?
