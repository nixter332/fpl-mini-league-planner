"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo, ThemeToggle, ErrorBox } from "@/components/ui";
import { ApiError, resolveInput } from "@/lib/api";
import { ordinal } from "@/lib/format";
import type { ResolveResponse } from "@/lib/types";

export default function MainPage() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [league, setLeague] = useState<ResolveResponse | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [slow, setSlow] = useState(false);

  // Free hosting sleeps when idle; start waking the backend while the user pastes their link.
  useEffect(() => {
    fetch("/api/health").catch(() => {});
  }, []);

  async function find(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setSlow(false);
    const timer = setTimeout(() => setSlow(true), 4000);
    setError(null);
    setLeague(null);
    setPicked(null);
    try {
      const res = await resolveInput(input.trim());
      if (res.type === "team") router.push(`/team/${res.id}`);
      else setLeague(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
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

      <form onSubmit={find} className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface p-4">
        <label htmlFor="team-link" className="text-[13px] font-semibold">Paste a link or team ID</label>
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
        <div className="text-[12.5px] leading-[1.45] text-text3">Works with your team link, your team ID, or your mini-league&apos;s link.</div>
        {busy && slow && (
          <div className="text-[12.5px] leading-[1.45] text-text2" role="status">
            Waking up the server. It sleeps when nobody&apos;s used it for a while, so the first visit can take up to a minute.
          </div>
        )}
      </form>

      {error && <ErrorBox message={error} />}

      {league && (
        <div className="flex flex-col gap-2 rounded-2xl border-[1.5px] border-accent-line bg-surface px-3.5 pb-3 pt-3.5" data-testid="league-members">
          <div className="flex flex-col gap-0.5">
            <div className="text-xs font-semibold text-good">League link found</div>
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
        </div>
      )}

      <div className="mt-auto text-center text-xs text-text3">We never ask for your FPL password.</div>
    </main>
  );
}
