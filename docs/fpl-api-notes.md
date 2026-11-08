# FPL API notes (confirmed against live responses)

Snapshot taken 2026-11-08, during GW10 of 2026/27 (the GW10 deadline had passed but the GW wasn't finished; GW9 was finished). Team 5179483, league 1883627. The raw responses are in `backend/tests/fixtures/`, and `manifest.json` lists them. To refresh them, run `python -m scripts.snapshot` (see CLAUDE.md).

Base URL: `https://fantasy.premierleague.com/api/`. Every endpoint below is public and needs no login.

## Headline findings

| Question | Answer |
| --- | --- |
| Purchase prices in picks? | **No.** Picks have only `element, position, multiplier, is_captain, is_vice_captain, element_type`. Derive them as described under [Purchase and sell prices](#purchase-and-sell-prices). |
| Defensive contribution field | `defensive_contribution` in `bootstrap-static` elements, `event/{gw}/live` stats and `element-summary` history. This is the **count of actions**, not points. It's 0 for every goalkeeper. `defensive_contribution_per_90` is also in bootstrap. |
| Defensive contribution scoring | `game_config.scoring.defensive_contribution = {DEF: 2, MID: 2, FWD: 2, GKP: 0}` points. The thresholds aren't in the API. GW9 live data shows the lowest scoring DEF count was 10 and the lowest MID count was 12, which matches the rule of 10 for DEF and 12 for MID/FWD. |
| Standings pagination | Query parameter `page_standings=N`, 50 rows per page, and `standings.has_next` says whether more pages exist. Confirmed on page 2 of league 314 (overall). League 1883627 has only one page (3 members). |
| Team strength | `strength` is **null** and `strength_attack_*` / `strength_defence_*` are **all 0** this season. Only `strength_overall_home` / `_away` (1–5) have values. The `win`, `draw`, `loss`, `points` and `played` fields are 0 too. Team strength must be built from fixture results. |
| Free-transfer cap | `game_config.rules.max_extra_free_transfers = 4`, so at most 5 can be banked. |
| Sell-on fee | `game_config.rules.transfers_sell_on_fee = 0.5` and `element_sell_at_purchase_price = false`, so you keep half of any price rise. |
| `ep_next` and `form` | `ep_next` = `form` × `chance_of_playing_next_round` / 100 (669/671 players). `form` = the player's points in GWs whose **deadline** fell in the last 30 days ÷ the number of fixtures his team had in those GWs (671/671 exact, including the in-progress GW). So FPL's `ep_next` can be rebuilt for any past GW from live data (see `docs/model.md`). |
| `ep_this` | After the deadline it equals `ep_next` for 660/671 players, so it's **not** a frozen pre-deadline prediction for the current GW. Don't use it as a benchmark. |
| Decimal fields | Many are **strings**, e.g. `expected_goals: "0.45"`, `selected_by_percent`, `form`, `ep_next`, `influence`. The `*_per_90` fields are real numbers. The models convert the strings to float. |

## Endpoints

### `bootstrap-static/` (about 2 MB)
Top-level keys: `chips, events, game_settings, game_config, phases, teams, total_players, element_stats, element_types, elements`.

- **events[]:** `id, name, deadline_time` (ISO, UTC, ends in `Z`), `finished, data_checked, is_previous, is_current, is_next`, plus `deadline_time_epoch, chip_plays, most_captained, ...`. During a live GW: `is_current=true, finished=false`, and the next GW has `is_next=true`.
- **elements[]** (671 players): `id, web_name, first_name, second_name, team, element_type, now_cost, cost_change_start, cost_change_event, status, chance_of_playing_next_round` (null means no news), `news, selected_by_percent, ep_next, ep_this, form, total_points, minutes, starts, goals_scored, assists, clean_sheets, goals_conceded, saves, bonus, bps, expected_goals, expected_assists, expected_goals_conceded, expected_*_per_90, clearances_blocks_interceptions, recoveries, tackles, defensive_contribution, defensive_contribution_per_90, penalties_order, ...`.
  - `status` values seen: `a` available, `d` doubtful, `i` injured, `s` suspended, `u` unavailable.
  - `defensive_contribution` = CBI + tackles for defenders. For example, Gabriel: 77 + 14 = 91.
  - New this season and not yet used: `price_change_percent, price_change_hourly_rate, price_change_projections`.
- **element_types[]:** `id` (1 GKP, 2 DEF, 3 MID, 4 FWD), `singular_name_short, squad_select` (2/5/5/3), `squad_min_play` (1/3/2/1), `squad_max_play` (1/5/5/3).
- **teams[]:** `id, code` (for shirts), `name, short_name, strength_overall_home/away`. Every other field is empty or 0 (see above).
- **game_config:** `rules` (squad size 15, `squad_team_limit` 3, `squad_total_spend` 1000, sell fee, free-transfer cap) and `scoring` (points per stat by position). `game_config.settings.price_change_deadlines` lists upcoming price-change times.
- **chips[]:** two of each chip per season. Wildcard and free hit cover GW2–19 and GW20–38; bench boost and triple captain cover GW1–19 and GW20–38.

### `fixtures/`
A list of all 380 fixtures, each with `id, event` (can be null if not scheduled, though none were), `kickoff_time, team_h, team_a, team_h_difficulty, team_a_difficulty, started, finished, finished_provisional, team_h_score, team_a_score, minutes, stats[]`. `stats` identifiers: goals_scored, assists, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, defensive_contribution. Every GW in the snapshot has 10 fixtures; there are no blank or double gameweeks scheduled yet.

### `event/{gw}/live/`
`{elements: [{id, stats, explain, modified}]}`.
- `stats`: minutes, goals_scored, assists, clean_sheets, goals_conceded, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, ICT, clearances_blocks_interceptions, recoveries, tackles, defensive_contribution, starts, expected_goals, expected_assists, expected_goal_involvements, expected_goals_conceded, total_points, in_dreamteam, played.
- `explain`: one entry per fixture, `{fixture, stats: [{identifier, points, value, points_modification}]}`. A stat appears only when it scored points. In a double gameweek there are two entries.

### `element-summary/{id}/`
`{fixtures, history, history_past}`.
- `fixtures[]`: upcoming matches, `id, event, team_h, team_a, is_home, difficulty, kickoff_time, event_name`.
- `history[]`: one row per past fixture, `round, fixture, opponent_team, was_home, minutes, total_points, value` (**price at that time**), every stat including `defensive_contribution`, and `selected, transfers_in/out`.
- `history_past[]`: per-season totals with `start_cost, end_cost`.

### `entry/{id}/`
`id, name` (team name), `player_first_name, player_last_name, started_event, current_event, last_deadline_bank, last_deadline_value, last_deadline_total_transfers, summary_overall_points, summary_overall_rank, leagues{classic[], h2h[], cup, ...}`. Classic leagues have `id, name, league_type` (`x` private, `s` system), `entry_rank, entry_last_rank, rank_count`.

### `entry/{id}/history/`
`{current, past, chips}`.
- `current[]`: `event, points, total_points, rank, overall_rank, bank, value, event_transfers, event_transfers_cost, points_on_bench`.
- `chips[]`: `{name, time, event}` with names `wildcard, freehit, bboost, 3xc`.
- **Wildcard weeks show `event_transfers: 0`.** This team made 26 transfers in GW6 (wildcard), and they're all in the transfers list, but history shows 0. Free-hit weeks probably behave the same way (not confirmed yet).

### `entry/{id}/transfers/`
A list, newest first: `element_in, element_in_cost, element_out, element_out_cost, entry, event, time`. It **includes wildcard transfers**. Prices are ints (tenths of a million).

### `entry/{id}/event/{gw}/picks/`
`{active_chip, automatic_subs, entry_history, picks}`. `picks[]` has 15 rows: `element, position` (1–11 starting, 12–15 bench), `multiplier` (0 bench, 1, 2 captain, 3 triple captain), `is_captain, is_vice_captain, element_type`. `entry_history` is that GW's row from history, including `bank` and `value`. Picks are visible once that GW's deadline passes, including for rivals.

### `leagues-classic/{id}/standings/?page_standings=N`
`{league, standings, last_updated_data, new_entries}`.
- `league`: `id, name, admin_entry, created, start_event, scoring, league_type, closed, code_privacy`.
- `standings`: `{has_next, page, results[]}` with 50 rows per page. Each row: `entry, entry_name, player_name, rank, last_rank, rank_sort, total, event_total`.
- `new_entries`: managers who joined since the last update, paginated the same way.

## Purchase and sell prices

The picks endpoint has no purchase price, so we'll derive it (this is phase 3 work and isn't built yet):
1. For each player in the squad, find the **latest** transfer with `element_in == player` and use `element_in_cost`.
2. If there's no such transfer, the player has been held since the manager's first GW, so the purchase price is that GW's price. For a GW1 team, that's `now_cost - cost_change_start`. In the snapshot, 3 of the 15 players (165, 8, 411) are this case.
3. Sell price = `purchase + floor((now − purchase) / 2)` if the price rose, otherwise `now`.

Check this against the FPL app's displayed squad value before trusting it. Free-hit transfers (not seen yet) would need excluding, because the squad reverts after a free hit.

## Free transfers

From `history.current`, roll forward a GW at a time: free transfers left = min(left − free ones used + 1, 5), with hits = `event_transfers_cost / 4`. Wildcard and free-hit weeks report 0 transfers, and the banked free transfers carry over. This is still to be built and checked against the app in phase 3.

## Caching policy (as built in `app/fpl/client.py`)

| Data | Expiry |
| --- | --- |
| `bootstrap-static`, `fixtures` | At the next deadline or after 6 h, whichever comes first |
| `event/{gw}/live`, `entry/*/event/{gw}/picks` for a finished, data-checked GW | Never |
| The same for an in-progress GW | 10 min (live) / 15 min (picks) |
| `entry/*`, `leagues-classic/*`, `element-summary/*` | 15 min |

User-Agent: `fpl-mini-league-planner/0.1 (read-only, public endpoints, cached)`. Throttling: at least 0.25 s between live requests, and 1 s between requests during bulk fetches (rivals' picks, standings pages). Retries happen on 429, 5xx and network errors (3 retries, waiting 1 s, 2 s, then 4 s, and honouring `Retry-After`). A 404 raises `FPLNotFound` without retrying. When the game is updating, FPL returns non-JSON, which raises a clear `FPLError`.
