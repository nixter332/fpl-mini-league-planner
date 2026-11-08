# Expected-points model (phase 2)

Code: `backend/app/model/`. Entry point: `project(data, train_through=gw, target_gws=[...])`, which returns one row per player per gameweek with the total xPts and each part.

## What it predicts

For each player, each fixture gets an expected-points figure, and the fixtures in a gameweek are added up. A double gameweek therefore counts twice and a blank counts 0. Each figure is kept as separate parts (appearance, goals, assists, clean sheet, goals conceded, saves, defensive contribution, bonus, cards), so later phases can explain a projection with the real numbers behind it.

| Part | How |
| --- | --- |
| Minutes (`minutes.py`) | Over the last 6 gameweeks where his team played, with recent weeks weighted more, the share of games he appeared in, started, and played 60+ minutes, plus his average minutes. A light prior (a fringe squad player) pulls down anyone with little history. This is the minutes gate. |
| Availability (`availability.py`) | Status `u` (left the club) → 0 for every fixture. A return date in the news ("Expected back 22 Nov", "Suspended until 29 Nov") → 0 before that date. Otherwise `chance_of_playing_next_round` applies to the next gameweek only. |
| Team strength (`team_strength.py`) | FPL's strength fields are empty this season, so each team gets attack and defence ratings from past matches, using a 70% xG / 30% real goals blend. Recent matches weigh more, each rating is adjusted for opponent strength, and every team is pulled toward average by 4 imaginary average matches. Expected goals for team T against opponent O = league home or away average × attack[T] × defence[O]. |
| Rates (`rates.py`) | xG, xA, bonus, yellow cards and saves per 90. Each one is his recent rate pulled toward his season rate, which is pulled toward a prior for his position and price. Pre-season prices are known in advance, so the price prior leaks nothing. |
| Goals and assists | Rate per 90 × expected minutes ÷ 90 × (team's expected goals in this fixture ÷ team's average). Points for a goal depend on position; an assist is 3. |
| Clean sheet | Chance of playing 60+ × P(opponent scores 0), using a Poisson distribution on the opponent's expected goals. |
| Goals conceded | GK and DEF lose 1 point per 2 goals conceded. Uses the expected value of ⌊goals ÷ 2⌋ under the same Poisson. |
| Saves | GKs: saves per 90, scaled by how many goals the opponent is expected to score. 1 point per 3 saves. |
| Defensive contribution | How often he has reached the threshold (10 for DEF, 12 for MID/FWD) in 60+ minute appearances, pulled toward the position average, × 2 points. |
| Double gameweeks | Each match carries 10% rotation risk, so a regular projects about 1.8× his single-gameweek figure. |

Point values come from `bootstrap-static` → `game_config.scoring`. Only the defensive contribution thresholds and the "per 3 saves" and "per 2 goals conceded" rules are constants, because the API doesn't provide them.

## No leakage

`history.py` rebuilds every player's past from `event/{gw}/live/` only. A prediction for GW k trains on gameweeks before k. From bootstrap the model uses only things known before the season (position, team, starting price) and, for live projections only, the current injury news. A test changes every number from GW k onwards, plus all of bootstrap's season totals, and checks that the GW k prediction doesn't move.

## The benchmark: FPL's ep_next, rebuilt for past gameweeks

The API only shows the current `ep_next`. We found that `ep_next` is just `form` × chance of playing (669 of 671 players match), and that `form` can be rebuilt exactly from live data (671 of 671). The rebuild is a player's points in the gameweeks whose deadlines fell in the last 30 days, divided by the number of matches his team played in them. So `backtest.py` can recreate FPL's prediction for any past gameweek, as it stood just before that deadline. Historical injury news isn't available, so in the backtest both our model and FPL's assume everyone is available.

## Backtest results (GW4–9, from the snapshot of 8 Nov 2026)

Mean absolute error per player per gameweek. Lower is better.

| Who's counted | Players-GWs | **Model** | FPL ep_next | Points per game |
| --- | --- | --- | --- | --- |
| Players who played | 1,842 | **2.00** | 2.30 | 2.18 |
| Every player with a fixture | 4,000 | **1.15** | 1.25 | 1.23 |

The model beats FPL's prediction in every one of the six gameweeks. On calibration, the model's average is 1.30 points against an actual average of 1.37, so it runs about 5% low.

Tuning note: the minutes prior weight (0.3) trades a little error for better calibration. A heavier prior has lower error, because predicting low suits this error measure, but it under-projects by 15%. That matters for the optimizer, where a −4 hit costs real points.

Run it with `cd backend && python -m scripts.backtest` (offline, from the fixtures), or add `--live` to use the cached API.

## Sanity checks (tests in `backend/tests/model/test_sanity.py`)

- An injured player (0% chance) projects 0 for the next gameweek. With a return date, he projects 0 until that date.
- A player whose team has a blank gameweek projects 0 for it.
- A double-gameweek regular projects 1.6–2.0× his single-gameweek figure.
- The top fit premium (Haaland) is in the top 5 projections over 4 gameweeks, and one quiet week (2 points, 0 xG) costs him less than 15% of his projection. This is the model-level guard against the v0 Haaland bug. The optimizer-level check ("isn't sold to fund two mid-price players") comes in phase 3.

## Known limits

- **Injuries with no return date** only affect the next gameweek. Their recent zero minutes still drag down later weeks, but a player who's out long-term will be over-projected after the first week.
- **New signings or players returning from long injuries** start near the fringe-player prior until they build up minutes.
- **Players who moved between PL clubs** mid-season are treated as playing for their current club when it comes to fixtures.
- Penalties, red cards, own goals and penalty saves aren't modelled separately. Penalties are partly included through xG.
- There have been no double or blank gameweeks so far this season, so those paths are tested only on made-up fixture lists.
