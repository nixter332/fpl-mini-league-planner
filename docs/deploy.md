# Deploying

- **Backend:** FastAPI on Render's **Starter** plan ($7/month), set up by `render.yaml` in the repo root. Every push to `main` redeploys it.
- **Frontend:** Next.js on Vercel's free Hobby plan. Vercel forwards `/api/*` to the backend, so browsers only ever talk to Vercel.

**Why not free?** (8 Nov 2026)
- Render's free plan gets a tenth of a CPU. The solver ran out of time there and returned "roll, +0.0" where a laptop finds +14.2.
- Hugging Face Spaces gives 2 free CPUs, but Docker Spaces now need its PRO plan ($9/month).

Starter has about half a laptop core and never sleeps. `SOLVER_TIME_SCALE=2` gives the solver twice its laptop time budget there. On any other host, set it to how many times slower than a laptop core the server is.

Facts to know:
- The server's disk is wiped on every redeploy or restart, so the FPL cache and saved reasons start empty again. The first plans after a deploy take a few seconds longer and may call Claude again.
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
5. Render shows what it found in `render.yaml`: one web service called **fpl-planner-api** on the **Starter** plan. Render asks for a card.
   - Give the Blueprint any name, for example `fpl-planner`.
   - Render asks for a value for **ANTHROPIC_API_KEY**. Paste your Claude key here. This is the only place it goes; it's never in the code.
   - Click **Deploy Blueprint** (or **Apply**).
6. Wait for the first build, about 3–5 minutes. Open the service and watch the **Logs** tab until it says `Application startup complete`.
7. Copy the service URL from the top of the page, something like `https://fpl-planner-api.onrender.com`. Then check two things in your browser:
   - `https://<your-url>/health` should show `{"status":"ok"}`
   - `https://<your-url>/api/team/5179483` should show your team as JSON. This proves FPL accepts requests from Render.

To set it up by hand instead, use **New**, then **Web Service**, and pick the repo. Enter the same settings by hand:

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | Starter |
| Environment variables | `PYTHON_VERSION` = `3.11.9`, `ANTHROPIC_API_KEY` = your key, `EXPLAIN_DAILY_CALLS` = `200`, `SOLVER_TIME_SCALE` = `2` |

## 2. Frontend on Vercel

1. Go to https://vercel.com/new. Your GitHub account is already linked from the Kaunsa Card app.
   - If **fpl-mini-league-planner** isn't in the list, click **Adjust GitHub App Permissions** and add it.
2. Click **Import** next to **fpl-mini-league-planner**.
3. Next to **Root Directory**, click **Edit** and choose `frontend`. The framework should show **Next.js**.
4. Open **Environment Variables** and add:
   - Name: `BACKEND_URL`
   - Value: the backend URL from step 1.7, with no slash at the end, for example `https://fpl-planner-api.onrender.com`
5. Click **Deploy** and wait about 1–2 minutes.
6. Open the Vercel URL, for example `https://fpl-mini-league-planner.vercel.app`, and try your team ID.

`BACKEND_URL` is read when the app is built. If you ever change it, redeploy: **Deployments**, then **⋯**, then **Redeploy**.

## 3. After that

- Every push to `main` redeploys both automatically.
- Send friends the Vercel URL. They paste their own team or league link; no login is needed.
- Track Claude spending at https://platform.claude.com (Billing, then Usage).

## Feedback and usage tracking (phase 6 groundwork)

**Feedback.** (Notes also go to PostHog with the `feedback_sent` event, where they are kept; Render logs expire.) Plan cards have "Was this plan useful? 👍 👎" with an optional note, and the team and plans screens have a "Send feedback" link. Feedback is anonymous: it carries the page, strategy, horizon, plan number and gameweek, but no team ID. The backend logs each one as a line starting with `FEEDBACK`, so in Render open **Logs** and search for `FEEDBACK`. There's no database yet; Render keeps logs for a limited time, so copy out anything worth keeping. Each visitor can send at most 20 an hour.

**PostHog (optional; off until a key is set).**
1. In PostHog, create a project for this app and copy its **Project API key** (it starts with `phc_`). This key is meant to be public: it can only send events.
2. In Vercel, open the project's **Settings**, then **Environment Variables**, and add:
   - `NEXT_PUBLIC_POSTHOG_KEY` = the key
   - `NEXT_PUBLIC_POSTHOG_HOST` = `https://eu.i.posthog.com`, *only* if your PostHog project is in the EU region (the default is US)

   Every event carries `app = fpl-mini-league-planner`, so the app can share a PostHog project with another app (filter on `app`).
3. Redeploy. `NEXT_PUBLIC_*` values are built into the app.

**What's tracked:**
- Page views
- `lookup`, `team_loaded`, `plans_loaded`
- `plan_setting_changed` (strategy, horizon, hits, chips)
- `plan_detail_opened`, `reason_shown` / `reason_missing`, `open_fpl_transfers`, `feedback_sent`
- `plan_shared` (share sheet or copy), `tips_dismissed`, `plan_opened` (a second or third plan opened)
- `nav_tab` (bottom tab bar), `demo_started` / `demo_ended` (the sample team; set `NEXT_PUBLIC_DEMO_TEAM` and `NEXT_PUBLIC_DEMO_LEAGUE` in Vercel to change which team it shows), `fpl_signup_opened`
- `plan_question` (kind: why, keep, hit or none), `week_loaded`, `rivals_loaded`, `compare_opened` / `compare_added`, `calendar_added`
- `league_invite_shared`, `invite_opened` (someone arrived by a league invite link, `/?league=…`; the league number is never sent)
- `app_error`: crashes and failed requests (server errors, rate limits, bad requests, no connection), with the endpoint and message. Digits of 3+ are replaced by `:id`, and at most 20 are sent per visit. In PostHog, filter on this event to see what breaks.

**Privacy.**
- No names, no team or league IDs. Page addresses are scrubbed before sending (`/team/5179483?league=…` becomes `/team/:id`).
- No autocapture, no session recording, no feature flags, and nobody is identified.

To check the privacy claim, run the test in `frontend/e2e/privacy.spec.ts`. It builds with a dummy key, intercepts everything sent to PostHog, and fails if a team or league ID appears.

## Optional Google sign-in

The start page offers **Sign in with Google (optional)**. Anyone can use the app without it. Signed-in users' usage events in PostHog carry their name and email; everyone else stays anonymous. Sign-in only identifies the person. It's separate from FPL, and we never ask for an FPL password. Sessions are kept in a signed cookie, so there's no database. The button stays hidden until the keys below are set.

**1. Create the Google sign-in client** (Google Cloud Console, free, about 10 minutes):
1. Go to https://console.cloud.google.com, create a project (for example "FPL Planner"), and select it.
2. Open **APIs & Services**, then **OAuth consent screen** (it may be called **Google Auth Platform**, then **Branding**):
   - user type **External**
   - app name "Mini-League Planner", your email as support and developer contact
   - no extra scopes (the defaults, email and profile, are all we use)
3. Open **Audience** (or the consent screen's publishing status) and click **Publish app**. Otherwise only test users you list can sign in. Basic sign-in (email and profile) needs no Google review.
4. Open **Credentials**, then **Create credentials**, then **OAuth client ID**, with type **Web application**. Add:
   - **Authorized JavaScript origins:** `https://fpl-mini-league-planner.vercel.app`
   - **Authorized redirect URIs:** `https://fpl-mini-league-planner.vercel.app/api/auth/callback/google`
   - (for local testing, also add `http://localhost:3000` and `http://localhost:3000/api/auth/callback/google`)
5. Click **Create** and copy the **Client ID** and **Client secret**.

**2. Add four environment variables in Vercel** (Settings, then Environment Variables). Keep the type **Secret** for the two secrets. None of these start with `NEXT_PUBLIC_`, so they never reach the browser.

| Name | Value |
| --- | --- |
| `GOOGLE_CLIENT_ID` | the Client ID |
| `GOOGLE_CLIENT_SECRET` | the Client secret |
| `NEXTAUTH_SECRET` | a long random string. Run `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"` and paste the output. Don't reuse a password. |
| `NEXTAUTH_URL` | `https://fpl-mini-league-planner.vercel.app` (needed so Google's return address matches) |

**3. Redeploy** (Deployments, then ⋯, then Redeploy). The button appears on the start page.

To test sign-in without Google, run `frontend/e2e/signin.spec.ts` with dummy values (see the comment in that file). It checks the button, the backend proxy, and the handover to Google.

## Alternative: Hugging Face Spaces (needs PRO)

The repo can also deploy to a Docker Space (`backend/Dockerfile`, `.github/workflows/deploy-hf-space.yml`). The workflow is skipped unless the `HF_SPACE` variable is set. If you use it, choose **CPU basic** hardware.


1. Create an account at https://huggingface.co/join.
2. Create the Space at https://huggingface.co/new-space:
   - Space name: `fpl-planner-api`
   - License: MIT, or any
   - SDK: **Docker**, with the **Blank** template
   - Hardware: **CPU basic · 2 vCPU · 16 GB · FREE**
   - Visibility: **Public**. Vercel can't reach a private Space, and the code is already public on GitHub.
   - Click **Create Space**.
3. In the Space, open **Settings**, then **Variables and secrets**, then **New secret**. Name it `ANTHROPIC_API_KEY` and paste your Claude key as the value.
4. Create a token so GitHub can upload to the Space:
   - Go to https://huggingface.co/settings/tokens and click **Create new token**.
   - Token type: **Write**. Name: `github-deploy`.
   - Click **Create** and copy the token.
5. On GitHub, open the repo's **Settings**, then **Secrets and variables**, then **Actions**:
   - On the **Secrets** tab, click **New repository secret**. Name it `HF_TOKEN` and paste the token.
   - On the **Variables** tab, click **New repository variable**. Name it `HF_SPACE` and set it to `<your-hf-username>/fpl-planner-api`.
6. Start the first deploy: go to **Actions**, then **Deploy backend to Hugging Face**, then **Run workflow**. After that, every push that changes `backend/` deploys automatically.
7. On the Space page, wait until the status goes from **Building** to **Running**, about 3–5 minutes the first time. The backend URL is `https://<your-hf-username>-fpl-planner-api.hf.space`. Check two links:
   - `<url>/health` should show `{"status":"ok"}`
   - `<url>/api/team/5179483` should show your team
