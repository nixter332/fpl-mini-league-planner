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

## Chips (9 Nov 2026)

The same 17 managers, GW5–GW9, no hits. The run also fixed a leak: simulated squads may now only contain players who existed that week. Wildcards had let the planner buy players added to the game later. Earlier runs had none of these: 0 of 891 transfers.

| Way of playing | Avg points | vs real manager | vs no transfers | Beat the real manager |
| --- | --- | --- | --- | --- |
| What managers really did | 258.8 | | +10.4 | |
| Keep the GW4 squad | 248.4 | −10.4 | 0.0 | 7 of 17 |
| Protect, no hits, no chips | 253.2 | −5.5 | +4.8 | 6 of 17 |
| **Protect, no hits, chips matched** | **258.9** | **+0.1** (±15) | +10.5 | 6 of 17 |
| Balanced, no hits, chips matched | 254.9 | −3.9 | +6.5 | 7 of 17 |
| Protect, no hits, planner chooses chips | 273.5 | +14.8 (±19) | +25.1 | 11 of 17 |

The scorer also matched FPL exactly on every real Bench Boost and Triple Captain week in these leagues (6 of 6), on top of the 113 normal weeks.

What it means:

1. **Chips matched is the fair test.** The planner gets the same chip in the same week as each real manager. It then scores level with the real managers. With chip timing taken out, its transfers, XI and captains are as good as these managers' were.
2. **"Planner chooses chips" isn't a fair win yet.**
   - It played a Wildcard in GW5 for 16 of the 17 managers.
   - It played Bench Boost in GW6 and Triple Captain in GW7 for 10 of them.

   The real managers played only Wildcards (8) and one Free Hit in this window, and still hold Bench Boost and Triple Captain for GW10–19. So the planner has simply spent more chips. The fair comparison is at GW19, when everyone must have used their first-half chips.
3. **The Wildcard bar is too low.** "Play it if it beats the best plan by 6 xPts over the horizon" fires almost every week early in the season, because a rebuild after a few weeks of data always looks better on paper. The "chips this week" card in the app only reports the number and doesn't recommend playing. Its threshold should still be raised before it's used as advice, and the GW19 rerun is how we'll tune it, along with the Bench Boost and Triple Captain keep values (8 and 6).

*Note:* this run decided Bench Boost and Triple Captain inside the model. The app now decides them after solving (see `docs/optimizer.md` → Chips), so the GW19 rerun will measure that version.

**Next for chips:** rerun after GW19 over GW5–19, with chips matched and with the planner choosing. By then every first-half chip has been used, and saved injury news covers GW11 onwards.

## Tuning on 412 managers (9 Nov 2026)

`python -m scripts.tune --from 4 --to 9` (results in `data/cache/tune/`, about 3 hours with 10 workers). 416 managers from three mini-leagues, overall ranks ~1M to ~10k, ~1k, and India's top 200 (`scripts/collect_managers.py`); 4 fail (their starting squad is infeasible). Each runs GW4–9 from their real GW3 squad, Protect, no injury news, with real points and auto-subs. Unused first-half chips at the end are credited at the sample's average real chip week (Bench Boost 17.6, Triple Captain 10.3) or an assumption (Free Hit 6, Wildcard 10), for planner and manager alike.

"Base" is the app's settings, with a user who follows the chip advice: play a Wildcard when the best plan with it beats the best without by 10+, a Free Hit by 4+.

| Setting | vs real, all (±3.5) | Leagues | ~1M–10k | ~1k | India top 200 | Hits |
| --- | --- | --- | --- | --- | --- | --- |
| Base | −88.7 | −17.2 | −78.4 | −110.0 | −97.4 | 0 |
| No chips | −53.2 | +0.6 | −35.2 | −78.2 | −65.3 | 0 |
| Chips matched to the real manager | −66.3 | −1.9 | −45.7 | −95.8 | −80.1 | 0 |
| Wildcard never | −71.0 | −5.7 | −57.3 | −87.5 | −83.0 | 0 |
| Wildcard bar 15 | −84.9 | −16.0 | −74.0 | −104.5 | −94.1 | 0 |
| Free Hit never | −82.1 | −15.9 | −71.8 | −104.6 | −90.0 | 0 |
| BB/TC keep low (4/3) | −89.2 | −18.2 | −77.7 | −110.9 | −98.7 | 0 |
| BB/TC keep high (12/9) | −86.0 | −19.8 | −74.0 | −109.8 | −94.7 | 0 |
| Saved FT worth 0 | −92.9 | −16.3 | −83.0 | −110.9 | −102.4 | 0 |
| Saved FT worth 3 | −85.3 | −25.6 | −73.2 | −103.1 | −95.0 | 0 |
| 1 hit allowed | −89.2 | −22.8 | −77.2 | −106.0 | −99.9 | 0.8 |
| 1 hit, margin 2 | −86.0 | −24.5 | −74.0 | −107.3 | −95.1 | 0 |
| 2 hits, margin 4 | −86.1 | −24.3 | −76.3 | −106.6 | −93.7 | 0 |

Points are totals over the 6 weeks, net of hits. The leagues group is small, so that column is noisy.

**What we learned**
- The chip advice loses points. The planner's Wildcard calls are the worst part: it advises one for 84% of managers, mostly in GW4, when projections are weakest. Never taking that advice gains 18; raising the bar to 15 gains only 4. Ignoring the Free Hit advice gains 7.
- With chips timed like the real managers, the planner is level with ordinary mini-league managers (−1.9) and well behind the top 10k, top 1k and India top 200.
- "No chips" looks best partly because unused chips are credited at an average real chip week, which is generous. It doesn't mean chips are worthless.
- How readily the planner plays Bench Boost and Triple Captain barely matters (within ±3).
- Hits don't pay: allowing one costs 0.5, and with a margin of 2 or more none are taken.
- A banked free transfer is worth keeping: valuing it at 0 costs 4; valuing it at 3 instead of 1.5 gains 3.
- The planner overrates the players it buys (`scripts/diagnose_transfers.py`, 911 transfers): projected 15.4, scored 11.6. Players sold are projected about right (10.1 vs 9.9). Each transfer gains +1.6 against +5.3 projected, and the gap is largest in GW4–6. Players bought who then didn't play are only 5% of transfers.

## Next

From GW11, FPL's injury news is saved before every deadline (`backend/data/news/`, by a scheduled GitHub Action), so later backtests can switch injury news back on with exactly what managers knew. Give the simulated planner the same chips in the same weeks as each real manager (chip-matching), so the comparison is fair.


Rerun at GW15 or later, when there will be twice as many weeks. Add Sticks and Stones (39 managers) for a bigger sample; it takes about 20 more minutes the first time. Check whether a margin on hits (for example, only take a hit when the projected gain is 6 or more) beats "no hits".
