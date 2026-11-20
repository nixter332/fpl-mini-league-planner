# Chip planner (phase 7)

Built 20 Nov 2026. Nikhil asked for it so he could time his Free Hit and Bench Boost before they expire after GW19.

Code:
- `backend/app/optimizer/chipplan.py`: the week values and the decision rule.
- `GET /api/chips` and `GET /api/chips/explain`: the API.
- `frontend/app/team/[id]/chips`: the page.
- `backend/scripts/backtest_chips.py`: the backtest.

## What it shows

For each chip a manager has left, every week from the next deadline to the end of the chip's window gets a value: what the chip is projected to add that week. The planner looks up to 9 weeks ahead, which is GW11–19 from GW11.

| Chip | Value of a week |
| --- | --- |
| Bench Boost | Projected points of the bench (all four) in the best lineup of the squad |
| Triple Captain | The captain's projected points again |
| Free Hit | A one-week solve for the best squad you can afford (selling value plus bank), minus your own best lineup |
| Wildcard | Not ranked. Its value lasts for weeks, and Wildcard advice lost 18 points in the 412-manager tuning (`docs/backtest-plans.md`) |

Rules:
- Every week is scored with the squad the manager has now. Transfers before then change the numbers, so the page is recomputed each week.
- Two chips never share a week. If their best weeks clash, the chip that loses less by moving takes its next-best week.
- Weeks within 1 point of the best count as close.
- The page names any blank or double gameweeks in the window. If there are none, it says so.

The planner's verdict is written from templates filled with its numbers. Claude adds a short reason for the best week from the same numbers, through the same trust check as plan reasons (`CHIP_SYSTEM` in `explainer.py`).

**Plan around it.** In Plans you can now choose a Bench Boost or Triple Captain week (`bboost=` / `tcap=` on `/api/plans`), as well as a Wildcard or Free Hit week. A chosen Bench Boost week counts the bench fully in the solver, so the plan builds the bench for it.

On Nikhil's team (20 Nov, 5-week Protect plan):
- **No chip:** the plan gains +16.4.
- **Bench Boost in GW13:** the boost adds +20.7 and the plan gains +33.5. The planner also swaps the backup keeper (Bentley → Trafford) in GW12.
- **Without preparing the bench:** the boost would add +5.7 that week.

**Deadline checklist.** The team page now opens with "Before the GW deadline", showing this week's transfer (Plan 1), captain and chip. Each row links to its screen.

**Reminders.** "Remind me before GW16" saves a calendar file with one event, "FPL GW16: play your Bench Boost", with reminders a day and 3 hours before.

## The gate: does the planner pick better weeks?

Phase 7's gate needs a backtest showing that the suggestions beat the chip-matched baseline. `python -m scripts.backtest_chips --from 5 --to 10` replays all 416 managers in the tuning sample:

1. Before each deadline from GW5 to GW10, using only data from before it, the planner scores every remaining week. It uses projections trained on earlier weeks, the manager's real squad, and no injury news.
2. It plays the chip if this week is the best of those weeks (the "best" rule), or if this week is within a point of the best (the "early" rule). GW10 plays it regardless.
3. Each week is then scored with real points: what the chip actually added that week.

Results (real points the chip added, per manager):

| Chip | Planner (best week) | Planner (early) | Random week | Best week in hindsight | Planner − random |
| --- | --- | --- | --- | --- | --- |
| Bench Boost | 10.9 | 11.2 | 10.9 | 19.2 | +0.0 (±0.6) |
| Triple Captain | 11.8 | 6.5 | 6.6 | 12.7 | +5.2 (±0.3) |
| Free Hit | −7.3 | −8.8 | −6.6 | 12.1 | −0.7 (±1.0) |

Chip-matched: managers who really played the chip in GW5–10, scored the same way.

| Chip | Managers | Their week | Planner's week | Planner − them |
| --- | --- | --- | --- | --- |
| Bench Boost | 70 | 20.8 | 15.1 | −5.7 (±2.5) |
| Triple Captain | 112 | 12.2 | 12.6 | +0.4 (±0.5) |
| Free Hit | 97 | 10.1 | −7.1 | −17.2 (±3.5) |

What it means:
- **Bench Boost:** the projected best week is no better than a random week. With no double gameweeks, benches differ little from week to week.
- **Triple Captain:** the +5.2 is one decision. 376 of 416 managers had GW7 picked, and GW7 was the big captain week (+12.5 on average). Managers' results all hang on that one week, so the ±0.3 understates the uncertainty. Against real managers it's level.
- **Free Hit:** the planner's Free Hit weeks lost points, and its projected gain (+7.8 a week) was far from the real one (−6.6). This backtest is unfair to it, because it has no injury news (it bought Isak, Saka and Fernandes in weeks they didn't play). Real managers' squads already reflected the news. It still can't say whether Free Hit timing works.
- **The ± ranges** are across managers. Managers in the same week share most of their result, so the real uncertainty is larger.

**Decision (20 Nov 2026): no chip passes the gate.** The page shows each week's projected value as a guide and never says "play now" or "hold" (`ADVISED` in `chipplan.py` is empty). It says so in plain words. The Free Hit values are labelled a best case.

**What does work: building the bench.** The 70 managers who played Bench Boost in GW5–10 got 20.8 from their bench that week, against 11.7 in their other weeks (+9.1 ± 2.1). Picking the week by projections alone added nothing, which suggests building the bench is what matters. That is why the Bench Boost card leads with "plan around it", and why Plans now accepts a chosen Bench Boost week.

## Limits and next

- **Short window:** GW5–10, not GW1–19. The planner had to play within 6 weeks, while real managers could wait.
- **No blanks or doubles:** none happened in the window, and none are scheduled before GW19. That's where Bench Boost and Free Hit timing usually matters.
- **No injury news:** it has been saved before every deadline since GW11 (`backend/data/news/`). After GW19:
  1. Give `backtest_chips.py` an option to use the saved news.
  2. Rerun it on GW11–19.
  3. Re-decide `ADVISED`, the Free Hit correction and Triple Captain.
