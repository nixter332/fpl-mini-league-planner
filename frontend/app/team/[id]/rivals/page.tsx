"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ErrorBox, Loading, ThemeToggle } from "@/components/ui";
import { PlayerTap, usePlayerInfo } from "@/components/PlayerInfo";
import { CardsSkeleton } from "@/components/Skeleton";
import { track } from "@/lib/analytics";
import { ApiError, getLeagueView, waitForRivals } from "@/lib/api";
import { ordinal, pts } from "@/lib/format";
import type { LeagueRow, LeagueViewResponse, Player, RivalsProgress } from "@/lib/types";

export default function RivalsPage() {
  return (
    <Suspense fallback={<Loading message="Loading your league…" />}>
      <RivalsScreen />
    </Suspense>
  );
}

function RivalsScreen() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const entry = Number(id);
  const leagueParam = search.get("league");
  const league = leagueParam === null ? null : Number(leagueParam);
  const [data, setData] = useState<LeagueViewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<RivalsProgress | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const info = usePlayerInfo(Math.max(0, (data?.rows.length ?? 1) - 1), `/team/${entry}/compare?${league !== null ? `league=${league}&` : ""}p=`);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    const fail = (e: unknown) => live && setError(e instanceof ApiError ? e.message : "Couldn't load your league.");
    getLeagueView(entry, league)
      .then(async (d) => {
        if (!live) return;
        setData(d);
        if (!d.ready && d.league) {
          // Show the table now; fill in projections once the rivals' squads are loaded.
          await waitForRivals(entry, d.league.id, (p) => live && setProgress(p), () => live);
          if (live) setData(await getLeagueView(entry, d.league.id));
        }
        track("rivals_loaded", { rivals: d.rows.length - 1 });
      })
      .catch(fail);
    return () => {
      live = false;
    };
  }, [entry, league]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <CardsSkeleton rows={3} message="Loading your league…" />;
  if (!data.league) {
    return (
      <main className="flex flex-col gap-3.5">
        <h1 className="m-0 font-display text-[26px] font-bold">Rivals</h1>
        <div className="rounded-2xl border border-line bg-surface p-3.5 text-[13px] text-text2">
          No mini-league is selected. Pick one in the League menu on the My team tab to see your rivals here.
        </div>
      </main>
    );
  }

  const me = data.rows.find((r) => r.is_me);
  const byProjection = [...data.rows].filter((r) => r.projected_total !== null).sort((a, b) => b.projected_total! - a.projected_total!);
  const myIndex = byProjection.findIndex((r) => r.is_me);
  const above = myIndex > 0 ? byProjection[myIndex - 1] : null;
  const below = myIndex >= 0 && myIndex < byProjection.length - 1 ? byProjection[myIndex + 1] : null;
  const headline =
    !data.ready || !me || me.projected_rank === null
      ? null
      : above
        ? `Projected after GW${data.gw}: ${ordinal(me.projected_rank)}, ${pts(above.projected_total! - me.projected_total!)} points behind ${above.name.split(" ")[0]}.`
        : below
          ? `Projected after GW${data.gw}: still 1st, ${pts(me.projected_total! - below.projected_total!)} points ahead of ${below.name.split(" ")[0]}.`
          : null;

  return (
    <main className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h1 className="m-0 font-display text-[26px] font-bold">Rivals</h1>
          <div className="truncate text-[13px] text-text2">{data.league.name} · projections for GW{data.gw}</div>
        </div>
        <ThemeToggle />
      </div>

      {!data.ready && (
        <div className="text-xs text-text3" role="status">
          Loading your rivals&apos; teams{progress ? `: ${progress.loaded} of ${progress.total}` : ""}…
        </div>
      )}
      {headline && (
        <div className="rounded-[14px] border border-cap-line bg-cap-bg px-3.5 py-3 text-sm leading-[1.4]" data-testid="rivals-headline">
          {headline}
        </div>
      )}

      <div className="flex flex-col gap-2" data-testid="rivals-table">
        {data.rows.map((r) => (
          <Row key={r.entry} row={r} gw={data.gw} open={open === r.entry} onToggle={() => setOpen(open === r.entry ? null : r.entry)} players={data.players} onPlayer={info.open} />
        ))}
      </div>
      <div className="text-center text-xs leading-snug text-text3">
        Projections use each manager&apos;s last known squad with their best XI and captain. Their transfers since the last deadline aren&apos;t visible.
      </div>
      {info.sheet}
    </main>
  );
}

function Row({ row, gw, open, onToggle, players, onPlayer }: {
  row: LeagueRow; gw: number; open: boolean; onToggle: () => void; players: Record<string, Player>; onPlayer: (p: Player) => void;
}) {
  const move = row.rank !== null && row.projected_rank !== null ? row.rank - row.projected_rank : 0;
  const names = (ids: number[]) =>
    ids.length
      ? ids.map((pid, i) => (
          <span key={pid}>
            {i > 0 ? ", " : ""}
            <PlayerTap player={players[pid]} onOpen={onPlayer} className="underline decoration-dotted underline-offset-2" />
          </span>
        ))
      : "nobody";
  return (
    <div className={`flex flex-col rounded-2xl bg-surface px-3.5 py-3 ${row.is_me ? "border-2 border-accent" : "border border-line"}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} data-testid="rival-row" className="flex items-center justify-between gap-3 text-left">
        <span className="flex min-w-0 items-center gap-3">
          <span className="w-7 shrink-0 font-display text-[15px] font-bold text-text2">{row.rank ?? "–"}</span>
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold">
              {row.name}
              {row.is_me ? " (you)" : ""}
            </span>
            <span className="truncate text-[11.5px] text-text3">{row.entry_name}</span>
          </span>
        </span>
        <span className="flex shrink-0 flex-col items-end">
          <span className="font-display text-[15px] font-bold">{row.total ?? "–"}</span>
          <span className="text-[11.5px] text-text3">
            {row.xpts !== null ? `+${pts(row.xpts)} proj` : "…"}
            {row.projected_rank !== null && (
              <span className={move > 0 ? "text-good" : move < 0 ? "text-bad" : ""}>
                {" "}
                → {ordinal(row.projected_rank)}
                {move > 0 ? " ▲" : move < 0 ? " ▼" : ""}
              </span>
            )}
          </span>
        </span>
      </button>
      {open && !row.is_me && row.xpts !== null && (
        <div className="mt-2 flex flex-col gap-1 border-t border-line pt-2 text-[12.5px] leading-[1.45] text-text2" data-testid="rival-details">
          <div>
            <b className="text-text">They have, you don&apos;t:</b> {names(row.differentials)}
          </div>
          <div>
            <b className="text-text">You have, they don&apos;t:</b> {names(row.my_differentials)}
          </div>
          <div>
            {row.captain !== null && (
              <>
                <b className="text-text">Captained last week:</b> {names([row.captain])} ·{" "}
              </>
            )}
            {row.shared} of 15 players shared
          </div>
        </div>
      )}
      {open && row.is_me && row.captain !== null && (
        <div className="mt-2 border-t border-line pt-2 text-[12.5px] text-text2" data-testid="rival-details">
          <b className="text-text">Best captain for GW{gw}:</b> {names([row.captain])}
        </div>
      )}
    </div>
  );
}
