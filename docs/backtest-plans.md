# Plan backtest

**Question (Nikhil, 8 Nov 2026):** if a manager had followed the planner every week, what would they have scored?

Code: `backend/app/optimizer/simulate.py` (scoring and week-to-week state) and `backend/scripts/backtest_plans.py`. Run it:

```
cd backend
python -m scripts.backtest_plans --leagues 1883627 1863820 1145494 --from 5 --to 9
python -m scripts.backtest_plans --report --out data/cache/backtest-plans.json   # tables only
```

## Method

For every member of three of Nikhil's leagues (SIUUUUU, Azad and Gulmohur: 17 managers), the simulation starts from the manager's real squad, bank and free transfers after GW4. Then, each week from GW5 to GW9:

1. Project points using only data from before that deadline.
2. Solve the app's Plan 1 for the chosen strategy (4-gameweek horizon). The manager's rivals are the other members of their league.
3. Make Plan 1's first-week transfers, and pick its XI, captain and vice.
4. Score the week with the real points. FPL's automatic substitutions and vice-captaincy apply, and hits are taken off.
5. Carry the squad, bank and free transfers into the next week.

**Scoring check.** Run on each manager's real picks, the scorer reproduced FPL's points exactly in 113 out of 113 manager-weeks (all weeks without chips).

**Comparisons:**
- **No transfers:** the starting squad kept all five weeks, with the model's XI and captain each week.
- **What the manager really did:** their FPL points, net of hits.

**Limits, all of which work against the planner:**
- Injury news is switched off. Today's news would leak the future, and there's no record of past news. Real managers knew who was injured; the simulation bought Isak 3 times in the week he didn't play.
- Chips aren't simulated. 9 of the 17 managers played a wildcard or free hit in this window.
- Prices are today's prices.

## Results (GW5–GW9, 17 managers)

Totals over the five weeks, net of hits:

| Way of playing | Avg points | vs real manager | vs no transfers | Beat the real manager | Hits taken |
| --- | --- | --- | --- | --- | --- |
| What managers really did | 258.8 | | +10.4 | | |
| No transfers | 248.4 | −10.4 | 0.0 | 7 of 17 | 0 |
| Protect | 244.9 | −13.8 | −3.5 | 4 of 17 | 40 |
| Balanced | 249.4 | −9.4 | +0.9 | 6 of 17 | 32 |
| Risky | 243.2 | −15.6 | −5.2 | 3 of 17 | 35 |
| Protect, saved transfer worth 0 | 248.9 | −9.8 | +0.5 | 5 of 17 | 35 |
| **Protect, no hits** | 251.8 | −7.0 | +3.4 | 5 of 17 | 0 |
| **Balanced, no hits** | 252.4 | −6.4 | +4.0 | 7 of 17 | 0 |
| Protect, no hits, saved transfer worth 0 | 253.4 | −5.4 | +4.9 | 6 of 17 | 0 |

Against the 8 managers who used no wildcard or free hit, Protect with no hits scored **+13.5 points** more than the real managers over the five weeks.

**How noisy is this?** The 95% range on "vs no transfers" is about ±10 points for all 17 managers, and about ±17 for the 8 without chips. Five weeks is a small sample, and one João Pedro haul in GW6 swung the result by around 7 points. **None of the differences between strategies is statistically clear.** What follows are directions, not proofs.

## What we learned

1. **Team selection is good.** On each manager's real squad, the model's XI and captain beat the manager's own choices by **+1.1 points a week** (85 manager-weeks, no chip weeks). The captaincy alone is worth +0.7 a week. The model chose the same captain as the manager 69% of the time.
2. **Hits didn't pay.** Protect took 40 hits, about 9 points per manager, and the extra transfers didn't earn them back. Every strategy did better without hits: Protect gained 7 points and Balanced gained 3. This is the "optimizer's curse": the solver takes a hit when its projected gain beats 4, and it picks the moves whose projections are luckiest, so the real gain is smaller than projected. **Change: the app now defaults to 0 hits.** Users can still allow them.
3. **Saving free transfers (worth 1.5):** no measurable effect either way. With no hits it made the same number of transfers (107). We keep it because it stops the transfers Nikhil flagged, such as swapping a backup keeper who never plays.
4. **Transfers in general** add only a few points over five weeks compared with keeping the squad, and without injury news the planner gives back some of that gain. In the app, with live injury news, it should do better. We'll know more once more weeks are played.

## Next

From GW11, FPL's injury news is saved before every deadline (`backend/data/news/`, by a scheduled GitHub Action), so later backtests can switch injury news back on with exactly what managers knew. Give the simulated planner the same chips in the same weeks as each real manager (chip-matching), so the comparison is fair.


Rerun at GW15 or later, when there will be twice as many weeks. Add Sticks and Stones (39 managers) for a bigger sample; it takes about 20 more minutes the first time. Check whether a margin on hits (for example, only take a hit when the projected gain is 6 or more) beats "no hits".
