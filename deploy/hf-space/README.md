---
title: FPL Planner API
emoji: ⚽
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Backend for the FPL Mini-League Planner
---

The API behind https://fpl-mini-league-planner.vercel.app. It reads only public Fantasy Premier
League endpoints (no logins), caches them, and builds transfer plans with an optimizer.

Code and docs: https://github.com/nixter332/fpl-mini-league-planner. This Space is updated
automatically from the `backend/` folder by `.github/workflows/deploy-hf-space.yml`.
