"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Bench, Pitch, kitFor, type PitchPlayer } from "@/components/Pitch";
import { ErrorBox, Facts, Loading, Segmented, ThemeToggle, Tile } from "@/components/ui";
import { ApiError, getTeam, waitForRivals } from "@/lib/api";
import { saveRecentTeam } from "@/lib/recent";
import { deadlineLabel, gwOf, ordinal, pts, signed } from "@/lib/format";
import type { Position, RivalsProgress, TeamResponse } from "@/lib/types";

export default function TeamPage() {
  return (
    <Suspense fallback={<Loading message="Loading your team…" />}>
      <TeamScreen />
    </Suspense>
  );
}

function TeamScreen() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const entry = Number(id);
  const leagueParam = search.get("league");
  const league = leagueParam === null ? null : Number(leagueParam);

  const [data, setData] = useState<TeamResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gwIndex, setGwIndex] = useState(0);
  const [mode, setMode] = useState<"xp" | "own">("xp");
  const [progress, setProgress] = useState<RivalsProgress | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    setProgress(null);
    const fail = (e: unknown) => live && setError(e instanceof ApiError ? e.message : "Couldn't load your team.");
    getTeam(entry, league)
      .then(async (d) => {
        if (!live) return;
        setData(d);
        saveRecentTeam({ entry, league: d.standing?.league.id ?? (league === 0 ? 0 : null), name: d.team_name });
        if (d.rivals && !d.rivals.ready) {
          // Show the team now; fill in the rival numbers once their squads are loaded.
          setProgress(d.rivals);
          await waitForRivals(entry, d.rivals.league_id, setProgress, () => live);
          if (live) setData(await getTeam(entry, d.rivals.league_id));
        }
      })
      .catch(fail);
    return () => {
      live = false;
    };
  }, [entry, league]);

  const positions = useMemo(() => {
    const map: Record<number, Position> = {};
    if (data) for (const p of Object.values(data.players)) map[p.id] = p.position;
    return map;
  }, [data]);
  // A fixed left-to-right spot per player, so switching gameweeks doesn't shuffle the pitch.
  const order = useMemo(() => Object.fromEntries((data?.squad ?? []).map((pid, i) => [pid, i])), [data]);

  if (error) return <ErrorBox message={error} action={<Link href="/">Try another team</Link>} />;
  if (!data) return <Loading message="Loading your team and your rivals…" />;

  const gw = data.gameweeks[gwIndex];
  const lineup = data.lineups[gwIndex];
  const standing = data.standing;
  const nRivals = standing?.n_rivals ?? 0;
  const activeLeague = standing?.league.id ?? 0;
  const rivalsLoading = !!data.rivals && !data.rivals.ready;
  const loaded = progress?.loaded ?? data.rivals?.loaded ?? 0;

  const token = (pid: number): PitchPlayer => {
    const p = data.players[pid];
    const g = gwOf(p, gw.id);
    return {
      id: pid,
      name: p.name,
      info: mode === "xp" ? g.fixture : rivalsLoading ? "Loading…" : `Owned ${p.rivals_owned}/${nRivals}`,
      value: mode === "xp" ? pts(g.xpts) : undefined,
      isCaptain: pid === lineup.captain,
      doubtful: p.doubtful,
      news: p.news,
      kit: kitFor(p, data.clubs),
    };
  };

  // Leaders start on Protect lead: differentials only add swing, and swing helps the chasers.
  const defaultStrategy = standing?.rank === 1 ? "protect" : "balanced";
  const plansHref = `/plans?team=${entry}&league=${activeLeague}&strategy=${defaultStrategy}&horizon=4&hits=0`;
  const gap = standing?.gap_to_first ?? null;

  return (
    <main className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-[3px]">
          <h1 className="m-0 truncate font-display text-xl font-bold">{data.team_name}</h1>
          {standing ? (
            <div className="text-[13px] text-text2">
              {standing.league.name} · {standing.rank ? ordinal(standing.rank) : "unranked"}
              {gap !== null && (
                <>
                  {" · "}
                  {gap > 0 ? (
                    <span className="font-semibold text-bad">{gap} pts behind 1st</span>
                  ) : (
                    <span className="font-semibold text-good">Top of the league</span>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="text-[13px] text-text2">No league selected · points only</div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Link href="/" className="py-1.5 text-[13px] font-semibold no-underline">Switch</Link>
          <ThemeToggle />
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs text-text3">
        League
        <select
          value={activeLeague}
          onChange={(e) => router.push(`/team/${entry}?league=${e.target.value}`)}
          className="h-8 min-w-0 flex-1 rounded-lg border border-line bg-surface px-2 text-[13px] text-text"
          aria-label="Mini-league"
        >
          {data.leagues.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
              {l.size ? ` (${l.size.toLocaleString("en-GB")})` : ""}
            </option>
          ))}
          <option value={0}>No league (points only)</option>
        </select>
      </label>

      {rivalsLoading && (
        <div className="flex items-center gap-2 text-xs text-text3" role="status" data-testid="rivals-progress">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-seg">
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${Math.round((100 * loaded) / Math.max(1, data.rivals!.total))}%` }} />
          </div>
          Loading rivals&apos; teams: {loaded} of {data.rivals!.total}
        </div>
      )}

      <div className="flex gap-1.5" role="group" aria-label="Gameweek">
        {data.gameweeks.map((g, i) => (
          <button
            key={g.id}
            type="button"
            aria-pressed={i === gwIndex}
            onClick={() => setGwIndex(i)}
            className={`h-9 flex-1 rounded-[10px] border text-[13px] font-semibold ${
              i === gwIndex ? "border-chip-on-bg bg-chip-on-bg text-chip-on-text" : "border-line bg-surface text-text"
            }`}
          >
            GW{g.id}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Tile label="Your projection" value={pts(lineup.xpts)} />
        <Tile label="Rivals' average" value={lineup.rivals_avg !== null ? pts(lineup.rivals_avg) : rivalsLoading ? "…" : "—"} />
        <Tile
          label="Edge"
          value={lineup.edge !== null ? signed(lineup.edge) : rivalsLoading ? "…" : "—"}
          tone={lineup.edge === null ? undefined : lineup.edge >= 0 ? "good" : "bad"}
        />
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-text3">{deadlineLabel(gw.name, gw.deadline, gwIndex)}</div>
        <Segmented
          label="Show on pitch"
          value={mode}
          onChange={setMode}
          options={[
            { key: "xp", label: "xPts" },
            { key: "own", label: "Rivals own" },
          ]}
        />
      </div>

      <Pitch players={lineup.starting.map(token)} positions={positions} order={order} />
      <Bench players={lineup.bench.map(token)} />

      <Link
        href={plansHref}
        className="flex h-12 shrink-0 items-center justify-center rounded-xl bg-accent text-[15px] font-semibold text-white no-underline"
      >
        See transfer plans
      </Link>
      <div className="text-center text-xs text-text3">
        {data.free_transfers} free transfer{data.free_transfers === 1 ? "" : "s"} · £{(data.bank / 10).toFixed(1)}m in the bank
      </div>
      {data.chips_left.length > 0 && (
        <div className="text-center text-xs text-text3" data-testid="chips-left">
          Chips left:{" "}
          {Object.entries(
            data.chips_left.reduce<Record<number, string[]>>((acc, c) => ({ ...acc, [c.stop]: [...(acc[c.stop] ?? []), c.label] }), {}),
          )
            .map(([stop, labels]) => `${labels.join(", ")} (until GW${stop})`)
            .join("; ")}
        </div>
      )}
      <Facts facts={data.facts} />
    </main>
  );
}
