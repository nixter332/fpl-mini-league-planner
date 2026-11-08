# Deploying (free tier)

- **Backend:** FastAPI on Render's free web service, configured by `render.yaml` in the repo root.
- **Frontend:** Next.js on Vercel's free Hobby plan. Vercel forwards `/api/*` to Render, so browsers only ever talk to Vercel.

Free-tier facts to know:
- Render puts the backend to sleep after about 15 minutes with no visitors. The next visit takes up to a minute while it wakes. The start page pings the backend as it opens and explains the wait if it's slow.
- Render's disk is wiped on every restart, so the FPL cache and saved reasons start empty again. The first plans after a restart take a few seconds longer and may call Claude again.
- Protection for the Claude credit:
  - each visitor gets at most 60 reason requests an hour
  - the whole app makes at most 200 new Claude calls a day (`EXPLAIN_DAILY_CALLS`)
  - each visitor can build at most 120 plan sets an hour
  - the prepaid Console balance is the hard cap

## 1. Backend on Render

1. Push your latest commits to GitHub. Render reads `render.yaml` from GitHub, not from your laptop.
2. Go to https://dashboard.render.com and click **New** (top right), then **Blueprint**.
3. Click **Connect GitHub** (or **Configure account** under GitHub).
   - GitHub asks you to install the Render app. Choose **Only select repositories**, pick **fpl-mini-league-planner**, then **Install**.
4. Back on Render, pick **fpl-mini-league-planner** from the list and click **Connect**.
5. Render shows what it found in `render.yaml`: one web service called **fpl-planner-api** on the **Free** plan.
   - Give the Blueprint any name, for example `fpl-planner`.
   - Render asks for a value for **ANTHROPIC_API_KEY**. Paste your Claude key here. This is the only place it goes; it's never in the code.
   - Click **Deploy Blueprint** (or **Apply**).
6. Wait for the first build, about 3–5 minutes. Open the service and watch the **Logs** tab until it says `Application startup complete`.
7. Copy the service URL from the top of the page, something like `https://fpl-planner-api.onrender.com`. Then check two things in your browser:
   - `https://<your-url>/health` should show `{"status":"ok"}`
   - `https://<your-url>/api/team/5179483` should show your team as JSON. This proves FPL accepts requests from Render.

If Render asks for a card for Blueprints: cancel, and instead use **New**, then **Web Service**, and pick the repo. Enter the same settings by hand:

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | Free |
| Environment variables | `PYTHON_VERSION` = `3.11.9`, `ANTHROPIC_API_KEY` = your key, `EXPLAIN_DAILY_CALLS` = `200` |

## 2. Frontend on Vercel

1. Go to https://vercel.com/new. Your GitHub account is already linked from the Kaunsa Card app.
   - If **fpl-mini-league-planner** isn't in the list, click **Adjust GitHub App Permissions** and add it.
2. Click **Import** next to **fpl-mini-league-planner**.
3. Next to **Root Directory**, click **Edit** and choose `frontend`. The framework should show **Next.js**.
4. Open **Environment Variables** and add:
   - Name: `BACKEND_URL`
   - Value: your Render URL from step 1.7, with no slash at the end, for example `https://fpl-planner-api.onrender.com`
5. Click **Deploy** and wait about 1–2 minutes.
6. Open the Vercel URL, for example `https://fpl-mini-league-planner.vercel.app`, and try your team ID.

`BACKEND_URL` is read when the app is built. If you ever change it, redeploy: **Deployments**, then **⋯**, then **Redeploy**.

## 3. After that

- Every push to `main` redeploys both automatically.
- Send friends the Vercel URL. They paste their own team or league link; no login is needed.
- Track Claude spending at https://platform.claude.com (Billing, then Usage).
