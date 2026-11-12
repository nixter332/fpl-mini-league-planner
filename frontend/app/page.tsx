"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo, ThemeToggle, ErrorBox } from "@/components/ui";
import { ApiError, resolveInput } from "@/lib/api";
import { track } from "@/lib/analytics";
import { forgetRecentTeam, loadRecentTeam, type RecentTeam } from "@/lib/recent";
import { DEMO_LEAGUE, DEMO_TEAM, endDemo, startDemo } from "@/lib/nav";
import { SignInCard } from "@/components/SignIn";
import { ordinal } from "@/lib/format";
import type { ResolveResponse } from "@/lib/types";

export default function MainPage() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [league, setLeague] = useState<ResolveResponse | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [choice, setChoice] = useState<ResolveResponse | null>(null);
  const [slow, setSlow] = useState(false);
  const [recent, setRecent] = useState<RecentTeam | null>(null);
  const [invited, setInvited] = useState(false); // arrived by a league invite link (/?league=123)
  const [help, setHelp] = useState(false);
  const [newbie, setNewbie] = useState(false);
  useEffect(() => setRecent(loadRecentTeam()), []);

  // An invite link has the league in it: find it straight away, so a friend only taps their name.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("league");
    if (!id || !/^\d{1,9}$/.test(id)) return;
    setInvited(true);
    track("invite_opened");
    lookup(`fantasy.premierleague.com/leagues/${id}/standings/c`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Free hosting sleeps when idle; start waking the backend while the user pastes their link.
  useEffect(() => {
    fetch("/api/health").catch(() => {});
  }, []);

  function find(e: React.FormEvent) {
    e.preventDefault();
    lookup(input.trim());
  }

  async function lookup(text: string) {
    endDemo();
    setBusy(true);
    setSlow(false);
    const timer = setTimeout(() => setSlow(true), 4000);
    setError(null);
    setLeague(null);
    setChoice(null);
    setPicked(null);
    try {
      const res = await resolveInput(text);
      track("lookup", { type: res.type });
      if (res.type === "team") router.push(`/team/${res.id}`);
      else if (res.type === "choice") setChoice(res);
      else setLeague(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      track("lookup_failed");
    } finally {
      clearTimeout(timer);
      setBusy(false);
      setSlow(false);
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-[18px] pt-2">
      <div className="flex items-center justify-between">
        <Logo />
        <ThemeToggle />
      </div>

      <div className="flex flex-col gap-2.5 pt-1">
        <h1 className="m-0 font-display text-[32px] font-bold leading-[1.1] tracking-[-0.5px]">Beat your mini-league, not the template.</h1>
        <p className="m-0 text-[15px] leading-[1.45] text-text2">Transfer plans built against your rivals&apos; squads, with the numbers behind every move.</p>
      </div>

      {invited && busy && !league && (
        <div className="rounded-2xl border border-line bg-surface px-3.5 py-3 text-[13px] text-text2" role="status" data-testid="invite-loading">
          Finding your league…
        </div>
      )}

      {recent && !league && !choice && !invited && (
        <div className="flex items-center justify-between gap-3 rounded-2xl border-[1.5px] border-accent-line bg-surface px-3.5 py-3" data-testid="recent-team">
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="text-xs text-text3">Welcome back</div>
            <div className="truncate text-[15px] font-semibold">{recent.name}</div>
            <button
              type="button"
              onClick={() => {
                forgetRecentTeam();
                setRecent(null);
              }}
              className="self-start text-xs text-text3 underline"
            >
              Not you? Forget this team
            </button>
          </div>
          <button
            type="button"
            onClick={() => {
              endDemo();
              track("recent_team_opened");
              router.push(`/team/${recent.entry}${recent.league !== null ? `?league=${recent.league}` : ""}`);
            }}
            className="h-11 shrink-0 rounded-[10px] bg-accent px-4 text-sm font-semibold text-white"
          >
            Open my team
          </button>
        </div>
      )}

      <form onSubmit={find} className={`${invited && league ? "hidden" : "flex"} flex-col gap-2.5 rounded-2xl border border-line bg-surface p-4`}>
        <label htmlFor="team-link" className="text-[13px] font-semibold">Paste a link or ID</label>
        <div className="flex gap-2">
          <input
            id="team-link"
            type="text"
            inputMode="url"
            autoComplete="off"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="fantasy.premierleague.com/entry/1234567/history"
            className="h-12 min-w-0 flex-1 rounded-[10px] border border-input-line bg-input px-3 text-sm text-text placeholder:text-text3"
          />
          <button type="submit" disabled={busy || !input.trim()} className="h-12 rounded-[10px] bg-accent px-4 text-sm font-semibold text-white disabled:opacity-60">
            {busy ? "Finding…" : "Find"}
          </button>
        </div>
        <div className="text-[12.5px] leading-[1.45] text-text3">Works with your team or mini-league link, or just the ID number.</div>
        <button type="button" aria-expanded={help} onClick={() => setHelp((v) => !v)} className="self-start text-[12.5px] font-semibold text-link" data-testid="id-help-toggle">
          {help ? "Hide help" : "Where is my link or ID?"}
        </button>
        {help && <IdHelp />}
        {busy && slow && (
          <div className="text-[12.5px] leading-[1.45] text-text2" role="status">
            Waking up the server. It sleeps when nobody&apos;s used it for a while, so the first visit can take up to a minute.
          </div>
        )}
      </form>

      {!invited && !league && !choice && (
        <div className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4" data-testid="demo-card">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="text-[13px] font-semibold">Just looking?</div>
              <div className="text-[12.5px] leading-[1.4] text-text3">See the planner on a real team and mini-league.</div>
            </div>
            <button
              type="button"
              onClick={() => {
                startDemo();
                track("demo_started");
                router.push(`/team/${DEMO_TEAM}?league=${DEMO_LEAGUE}`);
              }}
              className="h-10 shrink-0 rounded-[10px] border border-accent-line px-3.5 text-[13px] font-semibold text-link"
            >
              Try a sample team
            </button>
          </div>
          <button type="button" aria-expanded={newbie} onClick={() => setNewbie((v) => !v)} className="self-start text-[12.5px] font-semibold text-link" data-testid="new-to-fpl">
            {newbie ? "Hide" : "New to FPL?"}
          </button>
          {newbie && (
            <div className="flex flex-col gap-1.5 rounded-[10px] bg-surface2 p-3 text-[12.5px] leading-[1.5] text-text2" data-testid="fpl-intro">
              <div>
                <b className="text-text">Fantasy Premier League (FPL)</b> is the Premier League&apos;s free fantasy football game. You pick 15 real
                players within a £100m budget, and they score points for goals, assists and clean sheets in real matches.
              </div>
              <div>
                Each week you can change a player or two, and you choose a captain who scores double. Most people play in a{" "}
                <b className="text-text">mini-league</b> against friends or colleagues. This planner works out the moves that beat them.
              </div>
              <a href="https://fantasy.premierleague.com" target="_blank" rel="noopener noreferrer" onClick={() => track("fpl_signup_opened")} className="font-semibold">
                Create a free FPL team →
              </a>
              <div className="text-text3">You can join at any point in the season. Once you have a team, come back and paste its link.</div>
            </div>
          )}
        </div>
      )}

      {error && <ErrorBox message={error} />}

      {choice && (
        <div className="flex flex-col gap-2 rounded-2xl border-[1.5px] border-accent-line bg-surface px-3.5 pb-3 pt-3.5" data-testid="resolve-choice">
          <div className="text-[15px] font-semibold">{choice.id} is both a team and a league. Which did you mean?</div>
          <button
            type="button"
            onClick={() => router.push(`/team/${choice.id}`)}
            className="flex min-h-12 w-full flex-col items-start justify-center rounded-[10px] border border-line px-3 py-1.5 text-left"
          >
            <span className="text-xs text-text3">Team</span>
            <span className="text-sm font-semibold text-text">{choice.team_name} · {choice.manager_name}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setLeague({ ...choice, type: "league" });
              setChoice(null);
            }}
            className="flex min-h-12 w-full flex-col items-start justify-center rounded-[10px] border border-line px-3 py-1.5 text-left"
          >
            <span className="text-xs text-text3">League</span>
            <span className="text-sm font-semibold text-text">{choice.league_name}</span>
          </button>
        </div>
      )}

      {league && (
        <div className="flex flex-col gap-2 rounded-2xl border-[1.5px] border-accent-line bg-surface px-3.5 pb-3 pt-3.5" data-testid="league-members">
          <div className="flex flex-col gap-0.5">
            <div className="text-xs font-semibold text-good">{invited ? "You've been invited" : "League found"}</div>
            <div className="text-[15px] font-semibold">
              {league.league_name} · {league.members.length}
              {league.more_members ? "+" : ""} managers. Which one is you?
            </div>
          </div>
          <div className="flex max-h-[340px] flex-col gap-2 overflow-y-auto">
            {league.members.map((m) => (
              <button
                key={m.entry}
                type="button"
                onClick={() => setPicked(m.entry)}
                aria-pressed={picked === m.entry}
                className={`flex min-h-12 w-full items-center justify-between rounded-[10px] px-3 py-1.5 text-left ${
                  picked === m.entry ? "border-[1.5px] border-accent bg-row-on" : "border border-line bg-transparent"
                }`}
              >
                <span className="flex flex-col items-start gap-px">
                  <span className="text-sm font-semibold text-text">{m.player_name}</span>
                  <span className="text-xs text-text3">{m.entry_name}</span>
                </span>
                <span className="text-xs text-text2">{ordinal(m.rank)}</span>
              </button>
            ))}
          </div>
          {league.more_members && <div className="text-xs text-text3">Showing the top {league.members.length}. Not listed? Paste your team link instead.</div>}
          <button
            type="button"
            disabled={picked === null}
            onClick={() => picked !== null && router.push(`/team/${picked}?league=${league.id}`)}
            className="mt-1 flex h-[46px] items-center justify-center rounded-[10px] bg-accent text-[15px] font-semibold text-white disabled:opacity-50"
          >
            That&apos;s me, continue
          </button>
          <div className="text-center text-xs text-text3">Your row gives us your team ID. Your rivals load at the same time.</div>
          {invited && (
            <button type="button" onClick={() => { setInvited(false); setLeague(null); }} className="self-center text-xs text-text3 underline">
              Not your league? Paste your own link
            </button>
          )}
        </div>
      )}

      {!invited && <SignInCard />}

      <div className="mt-auto text-center text-xs text-text3">
        We never ask for your FPL password. <Link href="/privacy">Privacy</Link>
      </div>
    </main>
  );
}

/** How to find a team or league link. The FPL phone app shows no addresses, so this uses the website. */
function IdHelp() {
  return (
    <div className="flex flex-col gap-2.5 rounded-[10px] bg-surface2 p-3 text-[12.5px] leading-[1.5] text-text2" data-testid="id-help">
      <div>
        <b className="text-text">Easiest:</b> if a friend already uses the planner, ask them to tap <b className="text-text">Invite your league</b> on
        their team page. The link opens your league, and you just tap your name.
      </div>
      <div className="flex flex-col gap-1">
        <b className="text-text">Your league link</b>
        <ol className="m-0 flex list-decimal flex-col gap-0.5 pl-4">
          <li>
            Open <b className="text-text">fantasy.premierleague.com</b> in your browser (not the FPL app) and log in.
          </li>
          <li>
            Tap <b className="text-text">Leagues &amp; Cups</b>, then your mini-league.
          </li>
          <li>Copy the page address and paste it above. It looks like this:</li>
        </ol>
        <UrlExample before="fantasy.premierleague.com/leagues/" id="1234567" after="/standings/c" />
      </div>
      <div className="flex flex-col gap-1">
        <b className="text-text">Your team link</b>
        <ol className="m-0 flex list-decimal flex-col gap-0.5 pl-4">
          <li>
            On the same website, tap <b className="text-text">Points</b>.
          </li>
          <li>Copy the page address. The number after &ldquo;entry&rdquo; is your team ID:</li>
        </ol>
        <UrlExample before="fantasy.premierleague.com/entry/" id="1234567" after="/event/11" />
      </div>
    </div>
  );
}

function UrlExample({ before, id, after }: { before: string; id: string; after: string }) {
  return (
    <div className="overflow-x-auto whitespace-nowrap rounded-lg border border-line bg-input px-2.5 py-1.5 font-mono text-[11.5px] text-text3">
      {before}
      <span className="rounded bg-accent px-1 font-semibold text-white">{id}</span>
      {after}
    </div>
  );
}
