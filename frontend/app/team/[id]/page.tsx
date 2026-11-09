"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Bench, Pitch, kitFor, type PitchPlayer } from "@/components/Pitch";
import { ErrorBox, Facts, Loading, Segmented, ThemeToggle, Tile } from "@/components/ui";
import { ApiError, getAnalysis, getPlans, getReplacementReason, getTeam, waitForRivals, type ReplacementReason } from "@/lib/api";
import { Why } from "@/components/Why";
import { FixtureStrip } from "@/components/FixtureStrip";
import { Countdown } from "@/components/Countdown";
import { PriceMove } from "@/components/PriceMove";
import { Tips } from "@/components/Tips";
import { InstallHint } from "@/components/InstallHint";
import { Sheet } from "@/components/Sheet";
import { saveRecentTeam } from "@/lib/recent";
import { track } from "@/lib/analytics";
import { FeedbackLink } from "@/components/Feedback";
import { deadlineLabel, gwOf, money, ordinal, pts, signed } from "@/lib/format";
import type { AnalysisResponse, Player, Position, RivalsProgress, SpotOut, TeamResponse } from "@/lib/types";

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
  const [mode, setMode] = useState<"xp" | "own" | "weak">("xp");
  const [progress, setProgress] = useState<RivalsProgress | null>(null);
  const [rivalsFailed, setRivalsFailed] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  // Weak spots are worked out when first asked for (same strategy rule as the plans link).
  const rivalsReady = !data?.rivals || data.rivals.ready;
  useEffect(() => {
    if (mode !== "weak" || !data || !rivalsReady) return;
    let live = true;
    setAnalysisError(null);
    const strategy = data.standing?.rank === 1 ? "protect" : "balanced";
    getAnalysis(entry, data.standing?.league.id ?? 0, strategy)
      .then((a) => {
        if (!live) return;
        setAnalysis(a);
        track("analysis_loaded", { red: a.spots.filter((s) => s.level === "red").length, amber: a.spots.filter((s) => s.level === "amber").length });
      })
      .catch((e) => live && setAnalysisError(e instanceof ApiError ? e.message : "Couldn't find weak spots."));
    return () => {
      live = false;
    };
  }, [mode, data, rivalsReady, entry]);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    setProgress(null);
    setRivalsFailed(false);
    const fail = (e: unknown) => live && setError(e instanceof ApiError ? e.message : "Couldn't load your team.");
    getTeam(entry, league)
      .then(async (d) => {
        if (!live) return;
        setData(d);
        saveRecentTeam({ entry, league: d.standing?.league.id ?? (league === 0 ? 0 : null), name: d.team_name });
        const size = d.standing?.league.size ?? 0;
        track("team_loaded", { league_size: size === 0 ? "none" : size <= 5 ? "2-5" : size <= 20 ? "6-20" : size <= 50 ? "21-50" : "51+", rivals_ready: d.rivals?.ready ?? true });
        if (d.rivals && !d.rivals.ready) {
          // Show the team now; fill in the rival numbers once their squads are loaded.
          setProgress(d.rivals);
          try {
            await waitForRivals(entry, d.rivals.league_id, setProgress, () => live);
            if (live) setData(await getTeam(entry, d.rivals.league_id));
          } catch {
            // Keep the team on screen; only the rival numbers are missing.
            if (live) setRivalsFailed(true);
          }
        }
      })
      .catch(fail);
    return () => {
      live = false;
    };
  }, [entry, league]);

  // Start building the default plans as soon as the rivals are in, so "See transfer plans" opens
  // fast. The plans page asks for exactly the same set and picks up this request.
  const prefetchLeague = data ? (data.standing?.league.id ?? 0) : null;
  const prefetchStrategy = data?.standing?.rank === 1 ? "protect" : "balanced";
  useEffect(() => {
    if (prefetchLeague === null || !rivalsReady) return;
    const t = setTimeout(() => {
      getPlans({ team: entry, league: prefetchLeague, strategy: prefetchStrategy, horizon: 4, hits: 0, wildcard: null, freehit: null, chips: true }).catch(() => {});
    }, 1500);
    return () => clearTimeout(t);
  }, [entry, prefetchLeague, prefetchStrategy, rivalsReady]);

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

  const spots: Record<number, SpotOut> = Object.fromEntries((analysis?.spots ?? []).map((s) => [s.player, s]));
  const token = (pid: number): PitchPlayer => {
    const p = data.players[pid];
    const g = gwOf(p, gw.id);
    const spot = mode === "weak" ? spots[pid] : undefined;
    const weakInfo = !spot ? (analysis ? g.fixture : "…") : spot.level === "ok" ? g.fixture : spot.reason === "unavailable" ? "Unavailable" : `+${spot.gap.toFixed(1)} upgrade`;
    return {
      id: pid,
      name: p.name,
      info: mode === "xp" ? g.fixture : mode === "weak" ? weakInfo : rivalsLoading ? "Loading…" : `Owned ${p.rivals_owned}/${nRivals}`,
      value: mode === "xp" ? pts(g.xpts) : undefined,
      isCaptain: pid === lineup.captain,
      isVice: pid === lineup.vice,
      doubtful: p.doubtful,
      news: p.news,
      kit: kitFor(p, data.clubs),
      ring: spot && spot.level !== "ok" ? spot.level : undefined,
      onSelect: () => {
        setSelected(pid);
        track("player_details_opened", { mode, level: spot?.level ?? null });
      },
    };
  };
  const whatIfHref = (extra = "") => `/team/${entry}/what-if?league=${activeLeague}&strategy=${standing?.rank === 1 ? "protect" : "balanced"}${extra}`;

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

      <Countdown gw={data.gameweeks[0].id} deadline={data.gameweeks[0].deadline} />
      <Tips />
      <InstallHint />

      {rivalsLoading && (
        <div className="flex items-center gap-2 text-xs text-text3" role="status" data-testid="rivals-progress">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-seg">
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${Math.round((100 * loaded) / Math.max(1, data.rivals!.total))}%` }} />
          </div>
          {rivalsFailed ? "Couldn't load your rivals' teams. Refresh to try again." : <>Loading rivals&apos; teams: {loaded} of {data.rivals!.total}</>}
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
        <div className="text-xs text-text3">{gwIndex === 0 ? gw.name : deadlineLabel(gw.name, gw.deadline, gwIndex)}</div>
        <Segmented
          label="Show on pitch"
          value={mode}
          onChange={setMode}
          options={[
            { key: "xp", label: "xPts" },
            { key: "own", label: "Rivals own" },
            { key: "weak", label: "Weak spots" },
          ]}
        />
      </div>

      <Pitch players={lineup.starting.map(token)} positions={positions} order={order} />
      <Bench players={lineup.bench.map(token)} />
      {mode === "weak" && (
        <div className="text-xs leading-snug text-text3" data-testid="weak-legend">
          {analysisError ? (
            <span className="text-bad">{analysisError}</span>
          ) : !analysis ? (
            rivalsReady ? "Finding weak spots…" : "Waiting for your rivals' teams…"
          ) : (
            <>
              <span className="font-semibold text-[#F87171]">Red kit</span>: unavailable, or an affordable swap gains {6}+ points over the next {analysis.gws.length} GWs.{" "}
              <span className="font-semibold text-[#F59E0B]">Amber kit</span>: {3}+ points. Tap any player for the best replacements.
            </>
          )}
        </div>
      )}

      <Link
        href={plansHref}
        className="flex h-12 shrink-0 items-center justify-center rounded-xl bg-accent text-[15px] font-semibold text-white no-underline"
      >
        See transfer plans
      </Link>
      <Link
        href={whatIfHref()}
        onClick={() => track("what_if_opened", { from: "team" })}
        className="flex h-11 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-[14px] font-semibold no-underline"
      >
        Try your own transfers
      </Link>
      <Link href={`/team/${entry}/drafts?league=${activeLeague}`} className="-mt-1 self-center text-[13px] font-semibold no-underline" data-testid="drafts-link">
        My drafts →
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
      <FeedbackLink context={{ page: "team", gw: gw.id }} />
      {selected !== null && data.players[selected] && (
        <PlayerSheet
          player={data.players[selected]}
          spot={spots[selected]}
          analysis={analysis}
          weakMode={mode === "weak"}
          nRivals={nRivals}
          onClose={() => setSelected(null)}
          onShowWeak={() => setMode("weak")}
          tryHref={(into) => whatIfHref(`&m=${data.gameweeks[0].id}.${selected}.${into}`)}
          loadReason={() => getReplacementReason(entry, activeLeague, standing?.rank === 1 ? "protect" : "balanced", selected)}
        />
      )}
    </main>
  );
}

function PlayerSheet({
  player, spot, analysis, weakMode, nRivals, onClose, onShowWeak, tryHref, loadReason,
}: {
  player: Player; spot?: SpotOut; analysis: AnalysisResponse | null; weakMode: boolean; nRivals: number;
  onClose: () => void; onShowWeak: () => void; tryHref: (into: number) => string; loadReason: () => Promise<ReplacementReason>;
}) {
  const sell = player.sell_price ?? player.price;
  const hasOptions = weakMode && !!analysis && !!spot && spot.replacements.length > 0;
  const [reason, setReason] = useState<ReplacementReason | null>(null);
  useEffect(() => {
    if (!hasOptions) return;
    let live = true;
    loadReason().then((r) => live && setReason(r));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasOptions, player.id]);
  return (
    <Sheet title={player.name} onClose={onClose}>
      <div className="text-[13px] text-text2">
        {player.club} · {player.position} · sells for {money(sell)}
        {nRivals ? ` · ${player.rivals_owned}/${nRivals} rivals own him` : ""}
        <PriceMove change={player.price_change} long />
      </div>
      {player.news && <div className="rounded-lg bg-warn-bg px-3 py-2 text-[12.5px] text-warn-text">{player.news}</div>}
      <FixtureStrip gws={player.gws} />
      <div className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1 text-[13px]">
        {player.gws.slice(0, 4).map((g) => (
          <div key={g.gw} className="contents">
            <span className="text-text3">GW{g.gw}</span>
            <span className="truncate">{g.fixture}</span>
            <span className="text-right font-semibold">{pts(g.xpts)}</span>
          </div>
        ))}
      </div>
      {!weakMode || !analysis ? (
        <button type="button" onClick={onShowWeak} className="self-start text-[13px] font-semibold text-link">
          Show the best replacements →
        </button>
      ) : !spot || spot.replacements.length === 0 ? (
        <div className="text-[13px] text-text2">No affordable swap would improve your team over the next {analysis.gws.length} GWs. Keep him.</div>
      ) : (
        <div className="flex flex-col gap-2" data-testid="replacements">
          <Why explanation={reason} label={`Why ${analysis.players[spot.replacements[0].player]?.name ?? "the top swap"}`} />
          <div className="text-xs font-semibold text-text3">BEST REPLACEMENTS (next {analysis.gws.length} GWs, your whole team)</div>
          {spot.replacements.map((r) => {
            const c = analysis.players[r.player];
            return (
              <div key={r.player} className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-semibold">{c.name}</span>
                  <span className="truncate text-[11.5px] text-text3">
                    {c.club} · {money(c.price)}<PriceMove change={c.price_change} /> · {c.gws[0]?.fixture}
                    {nRivals ? ` · own ${c.rivals_owned}/${nRivals}` : ""}
                  </span>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="text-sm font-bold text-good">{signed(r.gain)}</span>
                  <Link href={tryHref(r.player)} onClick={() => track("what_if_opened", { from: "replacement" })} className="text-xs font-semibold no-underline">
                    Try in what-if →
                  </Link>
                </div>
              </div>
              <FixtureStrip gws={c.gws} />
              </div>
            );
          })}
          <div className="text-[11.5px] text-text3">Points are the change in your team&apos;s projected total (best XI and captain each week) if you make the swap now.</div>
        </div>
      )}
    </Sheet>
  );
}
