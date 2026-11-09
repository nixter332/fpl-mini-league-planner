# Optimizer (phase 3)

Code: `backend/app/optimizer/`. Command-line tool: `python -m scripts.plan` (see CLAUDE.md → Commands).

## Pipeline

1. **Squad state** (`state.py`): the squad and bank come from the latest picks. If that gameweek was a free hit, the previous gameweek's picks are used, because the squad reverts.
   - **Purchase price:** the most recent buy of each player in the transfer history, ignoring free-hit weeks. A player never transferred in uses the start-of-season price.
   - **Sell price:** you keep half of any rise, rounded down, and lose all of any fall.
   - **Free transfers:** worked out by replaying the history. Each week the count is min(unused + 1, 5). Wildcard and free-hit weeks keep the banked count without adding one. Nikhil confirmed the result in the app: 2 free transfers for GW11 and £1.1m in the bank.
2. **League ownership** (`ownership.py`): from rivals' latest picks, each player gets a starting share and a captaincy share, both between 0 and 1. Classic EO is kept for display.
3. **Player pool** (`inputs.py`): the current squad, plus the top 10 GK, 30 DEF, 30 MID and 20 FWD by xPts over the horizon, plus the 3 cheapest available players in each position. Players who can't be bought (status `u`) are left out.
4. **Multi-week model** (`solver.py`): for each player and gameweek it chooses squad, starting and captain, along with transfers in and out. For each gameweek it tracks free transfers, hits (exactly max(0, transfers − free)) and bank. It enforces:
   - 15 players with 2/5/5/3 per position, and at most 3 per club
   - an XI of 11 with exactly 1 GK, at least 3 DEF, 2 MID and 1 FWD
   - budget worked out with sell prices
   - free-transfer rollover, capped at 5
   - total hits over the horizon at most the max-hits setting
   - a player bought with a hit must start that week

   The vice-captain is picked afterwards as the best starter other than the captain. Keeping him out of the model makes it faster.
5. **Plans** (`plans.py`): the top 3 plans, plus the do-no-harm floor and the "roll the transfer" candidate. Every plan is re-checked against all FPL rules by `validate()`, which is independent of the solver.

## Objective

```
maximise  Σ_g 0.9^g · Σ_p xPts[p,g] · ( (1 − w·start_share_p) · start[p,g]
                                      + (1 − w·captain_share_p) · captain[p,g]
                                      + 0.1 · bench[p,g] )          (bench weight 0 for goalkeepers)
          − 4 · hits
          + 3 · free transfers still held after the last gameweek
subject to  plan xPts (XI + captain − 4·hits, undiscounted) ≥ no-transfer baseline xPts   (do no harm)
```

| Strategy | w | What it does on Nikhil's squad (GW11–14, 2 rivals) |
| --- | --- | --- |
| Protect | 0 | Pure points. Captains Haaland every week, keeps Raya and Bentley, and goes into GW14 with 2 free transfers. **+14.2 xPts** compared with no transfers. |
| Balanced | 0.15 | Takes a −4 hit for an extra differential and captains differentials (Van Hecke, De Cuyper, Tavernier). +10.7 xPts. |
| Risky | 0.33 | A −4 hit that also swaps Raya for Trafford, and differential captains. +7.5 xPts, with the most differential points. |

**Bench and saved transfers** (changed 8 Nov 2026 after Nikhil's review). The bench counts for 10% of its xPts because outfield subs do come on, but a backup goalkeeper counts 0: he almost never plays. Each free transfer still held after the horizon is worth 3 xPts (1.5 until 9 Nov 2026). Before this, a spare free transfer was worth nothing to the solver, so it spent one swapping the injured backup keeper Bentley for Trafford, who would also never play. Now a transfer has to beat the value of saving it. It started at 1.5, a common rule of thumb. Tuning on 412 managers over GW4–9 (`docs/backtest-plans.md`) found 3 gained about 3 points over 6 weeks and 0 lost 4, so it's now 3: the planner saves a transfer rather than making a small move.

**Default strategy.** The app starts managers who are 1st in their league on Protect lead and everyone else on Balanced. In expectation, rivals' points don't depend on your team, so a differential captain gives up expected points for swing. That suits a chaser, not a leader. In Nikhil's league, captaining Van Hecke (5.6) over Haaland (6.4), whom both rivals captain, costs about 0.8 points against both rivals on average.

Why the dial is gentler than the original spec (0 / 0.5 / 1): at 0.5, Balanced's best plan was 2.6 xPts *worse* than doing nothing, and at 1, Risky benched Haaland every week, because both rivals start him and that made his weight 0. The decision was made with Nikhil on 8 Nov 2026 and is recorded in `docs/SPEC.md`.

**Balanced and captaincy.** In this league both rivals captain Haaland, so at w = 0.15 his captain value (6.4 × 0.85 = 5.44) drops just below Van Hecke's (5.6). In bigger leagues, where captaincy shares are below 100%, Balanced moves away from the template captain less often.

## Chips

Added 9 Nov 2026 (Nikhil's request).

**Rules (from FPL's data).** Since 2025/26, every manager gets each chip twice: Wildcard, Free Hit, Bench Boost and Triple Captain once for GW1–19 and once for GW20–38. A chip not played by the end of its half is lost, and only one chip can be played per gameweek. `chips.py` works out the chips left from `bootstrap-static.chips` and the manager's history.

**Bench Boost and Triple Captain: the planner chooses the week, after solving.** First the transfers, lineups and captains are solved. Then, for each Bench Boost or Triple Captain left, every week of the plan gets a value:
- Bench Boost: the bench's points
- Triple Captain: the captain's points again

Each is weighted like the objective (strategy weight, decay). The chip is played in its best week, best first, with one chip per week, but only if that beats the chip's *keep value*: 8 xPts for Bench Boost and 6 for Triple Captain, roughly a good future use. The keep value is scaled by the weeks left in the chip's half after the plan ends (`min(1, weeks left / 6)`), so a chip about to expire is played rather than wasted. Users can switch this off ("don't play").

*Why after, not inside the model (9 Nov 2026):* the first version decided these chips inside the MILP. That made it much harder to solve. On Render's half CPU, Plan 1's transfers dropped from +14.2 to about +0.7, with the Bench Boost hiding it, and one plan came back as "roll +0.0". Deciding them afterwards costs no solver time. What's lost is buying bench players just for a Bench Boost week, which is a small loss.

**Wildcard and Free Hit: you choose.** A Wildcard's benefit lasts long after a 4-week plan ends, so a 4-week model deciding on its own would be guessing. The user picks the gameweek (`wildcard=` / `freehit=` on `/api/plans`):
- **Wildcard:** unlimited free transfers that week with no hits. The banked free transfers are kept, with no +1. The new squad stays.
- **Free Hit:** a separate one-week squad. It must cost no more than the bank plus the squad's selling value, it takes no hits, the bank and banked free transfers are unchanged, and the old squad is back the week after.

*No chip advice (9 Nov 2026).* The app used to show what a Wildcard or Free Hit this week would add, with a "Plan with it" button. On 412 managers over GW4–9 (`docs/backtest-plans.md`), following that advice cost 18 points over 6 weeks for the Wildcard and 7 for the Free Hit. The planner advised a Wildcard for 84% of managers, mostly in GW4, when projections are weakest, and a higher bar barely helped. So the card and `/api/chip-advice` were removed. You can still choose either chip, and the plans are built around it.

**Reported numbers.** A plan's xPts gain includes chip points, and each chip week shows the points the chip adds (`chip_xpts`), so "+27.1, of which Bench Boost +12.9" is visible. `validate()` checks the chip rules independently: chips available, each used once per half, no hits in Wildcard or Free Hit weeks, Free Hit affordability, and free transfers kept.

**Speed.** Bench Boost and Triple Captain cost nothing extra, since they're decided after solving. A chosen Free Hit adds a one-week squad to the model: about 4 s against 3 s on a laptop.

## Reported numbers

- **xPts gained**: plan xPts minus the best points-only lineup with no transfers, over the horizon, net of hits. The do-no-harm rule makes this ≥ 0 for every plan.
- **Differential xPts gained**: the same comparison, counting only the share of each player's points that rivals won't also get, i.e. xPts × (1 − share). This measures swing potential. It does **not** measure expected margin, because in expectation rivals' points don't depend on your team.

## Speed

CBC (bundled with PuLP) was 3–5× faster than HiGHS on this model, at about 1.2 s against about 5 s per solve. A full set of plans is 4–5 solves, so `make_plans` has a 3.5 s budget:
- the baseline takes about 0.2 s
- plan 1 gets up to 2 s, which is enough to prove it's the best on Nikhil's squad
- plans 2–3 share the rest
- "roll" solves alongside the chain

A plan that stops at its time limit is the best valid plan found so far; in tests that was within about 0.04 xPts of the true best. These plans are shown as "best found within the time limit" and are still fully validated. A whole run (projection, pool and 3 plans) takes about 4 s on Nikhil's laptop; there's a test for under 5 s.

The things I tried that didn't help: HiGHS settings, continuous transfer variables, a smaller pool, CBC threads (hangs on Windows), CBC preprocessing and cut options, and continuous lineup variables.

`pulp` is pinned below version 4 because PuLP 4 removes the bundled CBC.

## Tests (`backend/tests/optimizer/`)

- Your real squad gets valid plans for all three strategies, and the whole run takes under 5 s.
- 6 random valid squads, with random bank, free transfers, strategy and max hits, always get valid plans.
- The Haaland check: Protect and Balanced never sell him, but if he's projected 0, Protect sells him straight away.
- Protect captains the top projection every week.
- Do no harm holds for every plan.
- Risky trades xPts for differentials compared with Protect.
- Plans have different first-week moves.
- A player bought with a hit starts. With max hits 0, no hits are taken.
- When transfers gain nothing, "roll" is offered.
- `validate()` catches a benched captain and an overspent bank.
- Transfers are paired like-for-like by position.

## Known limits

- Chips (wildcard, free hit, bench boost, triple captain) aren't planned.
- Price changes during the horizon are ignored: a player bought within the plan is assumed to sell for the price paid.
- Rivals' squads are last week's, and transfers made since the deadline aren't visible.
- One-off FPL rule changes (e.g. a season's free-transfer top-up) aren't in the API, so the free-transfer count could be wrong in those weeks.
- Fetching 20 rivals' picks takes about 20 s on a cold cache, because bulk calls are throttled to 1 per second. Phase 5 should pre-fetch them, or show the plans first and add league ownership after.
