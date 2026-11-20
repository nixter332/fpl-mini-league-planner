"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bench, Pitch, kitFor, type PitchPlayer } from "@/components/Pitch";
import { track } from "@/lib/analytics";
import { ApiError, getBenchBuild } from "@/lib/api";
import { gwOf, money, pts, signed } from "@/lib/format";
import type { BenchBuildResponse, ChipName, ChipSquad, ChipWeek, Club, Player, Position, Strategy } from "@/lib/types";

const PLANS_REACH = 5; // Plans look 5 gameweeks ahead

interface Props {
  chip: ChipName;
  week: ChipWeek;
  first: number; // the next deadline's gameweek
  players: Record<number, Player>;
  clubs: Record<string, Club>;
  team: number;
  league: number | null;
  strategy: Strategy;
  onOpen: (p: Player) => void;
}

/** The squad behind one week of a chip, on a pitch. Free Hit: its one-week squad. Bench Boost:
 * your squad now, or (for weeks Plans can reach) the squad with the bench built for it. */
export function ChipSquadView({ chip, week, first, players, clubs, team, league, strategy, onOpen }: Props) {
  const isBoost = chip === "bboost";
  const canBuild = isBoost && week.gw < first + PLANS_REACH;
  const [mode, setMode] = useState<"now" | "built">("now");
  const [built, setBuilt] = useState<BenchBuildResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMode("now");
    setBuilt(null);
    setError(null);
  }, [week.gw, chip]);

  useEffect(() => {
    if (mode !== "built" || !canBuild) return;
    let live = true;
    getBenchBuild(team, league, strategy, week.gw)
      .then((b) => {
        if (!live) return;
        setBuilt(b);
        track("chip_bench_built", { weeks_ahead: week.gw - first, gain: Math.round(b.boost_xpts - b.boost_now_xpts) });
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Couldn't build the bench."));
    return () => {
      live = false;
    };
  }, [mode, canBuild, team, league, strategy, week.gw, first]);

  const all = built && mode === "built" ? { ...players, ...built.players } : players;
  const squad: ChipSquad | null = mode === "built" ? built?.squad ?? null : week.squad;
  const positions: Record<number, Position> = Object.fromEntries(Object.values(all).map((p) => [p.id, p.position]));
  const token = (sq: ChipSquad) => (pid: number): PitchPlayer => {
    const p = all[pid];
    const g = gwOf(p, week.gw);
    return {
      id: pid,
      name: p.name,
      info: g.fixture,
      value: pts(g.xpts),
      isCaptain: pid === sq.captain,
      isVice: pid === sq.vice,
      isNew: p.sell_price === null, // not in your squad now
      doubtful: p.doubtful,
      news: p.news,
      kit: kitFor(p, clubs),
      onSelect: () => onOpen(p),
    };
  };
  const name = (pid: number) => all[pid]?.name ?? "?";

  return (
    <div className="flex flex-col gap-2" data-testid="chip-squad">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-semibold text-text3">
          {chip === "freehit" ? `FREE HIT SQUAD · GW${week.gw}` : `YOUR SQUAD · GW${week.gw}`}
        </div>
        {chip === "freehit" && week.squad?.cost != null && week.squad.budget != null && (
          <div className="text-[11.5px] text-text3">
            {money(week.squad.cost)} of your {money(week.squad.budget)}
          </div>
        )}
      </div>

      {isBoost && (
        <div className="flex gap-1 rounded-xl bg-seg p-1" role="group" aria-label="Bench Boost squad">
          {([["now", "Your bench now"], ["built", "Bench built for it"]] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={mode === key}
              disabled={key === "built" && !canBuild}
              onClick={() => setMode(key)}
              className={`min-h-9 flex-1 rounded-[9px] text-[12.5px] font-semibold disabled:opacity-40 ${mode === key ? "bg-accent text-white" : "bg-transparent text-text2"}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {isBoost && !canBuild && (
        <div className="text-[12px] text-text3">
          A bench can be built for GW{first} to GW{first + PLANS_REACH - 1}. GW{week.gw} can be built from GW{week.gw - PLANS_REACH + 1}.
        </div>
      )}

      {mode === "built" && !built && !error && (
        <div className="flex flex-col gap-1.5 py-2" role="status" aria-label="Building the bench">
          <div className="text-[12.5px] text-text3">Planning transfers to build your bench for GW{week.gw}…</div>
          <div className="h-2.5 w-full animate-pulse rounded bg-line" />
        </div>
      )}
      {mode === "built" && error && <div className="text-[12.5px] text-bad">{error}</div>}

      {mode === "built" && built && (
        <div className="flex flex-col gap-1.5 rounded-xl bg-pill px-3 py-2.5 text-[12.5px] leading-[1.45]" data-testid="chip-bench-moves">
          {built.weeks.map((w) => (
            <div key={w.gw}>
              <span className="font-semibold">GW{w.gw}:</span>{" "}
              {w.moves.length ? w.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ") : "no transfer"}
              {w.hits ? ` (−${4 * w.hits})` : ""}
            </div>
          ))}
          <div className="text-text2">
            The boost adds <b className="text-text">{signed(built.boost_xpts)}</b>, against {signed(built.boost_now_xpts)} with your bench now.
            The whole plan gains {signed(built.plan_gain)} over {built.horizon} GWs.
          </div>
          <Link
            href={`/plans?team=${team}${league !== null ? `&league=${league}` : ""}&strategy=${built.strategy}&horizon=${built.horizon}&hits=0&bboost=${built.gw}`}
            onClick={() => track("chip_plan_opened", { chip, weeks_ahead: week.gw - first, from: "bench" })}
            className="self-start font-semibold no-underline"
          >
            Open this plan →
          </Link>
        </div>
      )}

      {squad && (
        <>
          {chip === "freehit" && (
            <div className="text-[12.5px] text-text2">
              Projected {pts(squad.xpts)} with the captain, {signed(week.xpts)} on your own best lineup. New players have a green outline.
            </div>
          )}
          {chip === "3xc" && (
            <div className="text-[12.5px] text-text2">
              {name(squad.captain)} as triple captain adds {signed(week.xpts)}.
            </div>
          )}
          {isBoost && mode === "now" && (
            <div className="text-[12.5px] text-text2">With Bench Boost all 15 score: your bench adds {signed(week.xpts)}.</div>
          )}
          <Pitch players={squad.starting.map(token(squad))} positions={positions} />
          <Bench players={squad.bench.map(token(squad))} />
        </>
      )}

      {week.gw > first && (
        <div className="text-[11.5px] leading-snug text-text3">
          A squad for GW{week.gw} is a draft: injuries, prices and form will change it. Check it again in the week you play.
        </div>
      )}
    </div>
  );
}
