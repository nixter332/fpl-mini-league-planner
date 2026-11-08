# Lessons from the v0 prototype (fpl_tactical_planner)

The old Streamlit app is not reused. These are the rules worth keeping and the mistakes to avoid.

## Keep (re-implement cleanly)

- Squad rules: 15 players (2 GK, 5 DEF, 5 MID, 3 FWD), max 3 per club, starting XI of 11 with 1 GK, at least 3 DEF, 2 MID, 1 FWD; one captain and one vice, both starting.
- Budget uses **sell prices**: you keep half of any price rise (rounded down), and lose all of a price fall.
- Free transfers roll over: next = min(unused + 1, 5). Check this against the current season's rules.
- Players bought with a hit (a -4) must start that gameweek; free-transfer buys may be benched.
- Blank gameweeks: a player with no fixture scores 0 and should not be started if any alternative exists.
- Minutes gate: heavily discount players with very few recent minutes.
- Team clean-sheet strength from the team's own record, not just FPL's 1–5 difficulty rating.
- "Next actionable gameweek" logic: if the current gameweek is finished, plan for the next one.

## Avoid (bugs and weak spots found in v0)

1. **Sell prices were probably wrong.** The public picks endpoint does not return purchase prices, so v0 read 0 and computed roughly half-price sell values. Derive purchase prices from the manager's transfer history and players' price history instead.
2. **Double gameweeks counted as one game.** v0 averaged the two fixture difficulties. Expected points must be summed per fixture.
3. **One lineup for the whole horizon.** v0 picked a single XI and captain from a 5-week total, and gave bench players zero value. Lineup and captain must be chosen per gameweek.
4. **Greedy week-by-week passes.** v0 solved one week at a time, so it could never plan "save a transfer now, make two next week". Use one multi-week model.
5. **Unlimited hits.** The "Pure Max" mode could take -12s. Always cap hits.
6. **Noisy predictions.** v0 leaned on the last 5 gameweeks of points; xG/xA was only a fallback. It sold Haaland to fund two mid-price players. The new model is built on xG/xA, minutes and fixtures, and must pass the sanity checks in `docs/SPEC.md`.
7. **Wrong field for defensive contributions.** v0 read a field called `dc` that doesn't exist, so the signal was always 0. Check the real field name in `bootstrap-static` (likely `defensive_contribution`).
8. **Overall ownership instead of league ownership.** "Rank Chaser" used global ownership under 10%. The new optimizer uses ownership within the user's mini-league.
9. **~215 API calls per run.** Fetch shared data once per gameweek for all users, and use `event/{gw}/live/` for per-gameweek stats instead of one call per player.
10. **Free transfers typed in by hand.** Derive them from the manager's history.
