"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Bench, Pitch, kitFor, type PitchPlayer } from "@/components/Pitch";
import { BackLink, ErrorBox, Loading, Segmented, ThemeToggle } from "@/components/ui";
import { Why, useExplanation } from "@/components/Why";
import { PlanFeedback } from "@/components/Feedback";
import { SharePlan } from "@/components/SharePlan";
import { usePlayerInfo } from "@/components/PlayerInfo";
import { track } from "@/lib/analytics";
import { ApiError, getPlans, readPlanParams } from "@/lib/api";
import { CHIP_LABELS, gwOf, pts, strategyLabel } from "@/lib/format";
import type { PlansResponse, Position } from "@/lib/types";

export default function PlanDetailPage() {
  return (
    <Suspense fallback={<Loading message="Loading plan…" />}>
      <PlanDetail />
    </Suspense>
  );
}

function PlanDetail() {
  const { rank } = useParams<{ rank: string }>();
  const search = useSearchParams();
  const params = readPlanParams(search);
  const [data, setData] = useState<PlansResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"before" | "after">("after");
  const explanation = useExplanation(params, Number(rank));
  const info = usePlayerInfo(data?.standing?.n_rivals ?? 0, `/team/${params.team}/compare?${params.league !== null ? `league=${params.league}&` : ""}p=`);

  useEffect(() => {
    getPlans(params)
      .then((d) => {
        setData(d);
        track("plan_detail_opened", { rank: Number(rank), strategy: d.strategy });
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load the plan."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search.toString()]);

  const positions = useMemo(() => {
    const map: Record<number, Position> = {};
    if (data) for (const p of Object.values(data.players)) map[p.id] = p.position;
    return map;
  }, [data]);

  const back = `/plans?${search.toString()}`;
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading message="Loading plan…" />;
  const plan = data.plans.find((p) => p.rank === Number(rank));
  if (!plan) return <ErrorBox message="That plan isn't available any more." action={<a href={back}>Back to all plans</a>} />;

  const lineup = view === "after" ? plan.after : plan.before;
  const gw = lineup.gw;
  const before = new Set([...plan.before.starting, ...plan.before.bench]);
  const name = (id: number) => data.players[id]?.name ?? `#${id}`;
  const first = plan.gameweeks[0];
  // This week's swaps: a new player takes the spot of the one he replaces.
  const replaces = Object.fromEntries(first.moves.map((m) => [m.player_in, m.player_out]));
  const sold = new Set(first.moves.map((m) => m.player_out));
  const baseOrder = [...before].sort((a, b) => a - b);
  const order: Record<number, number> = Object.fromEntries(baseOrder.map((pid, i) => [pid, i]));
  for (const [pin, pout] of Object.entries(replaces)) order[Number(pin)] = order[pout] ?? Number(pin);
  const n = data.standing?.n_rivals ?? 0;

  const token = (pid: number): PitchPlayer => {
    const p = data.players[pid];
    const g = gwOf(p, gw);
    return {
      id: pid,
      name: p.name,
      info: g.fixture,
      value: pts(g.xpts),
      isCaptain: pid === lineup.captain,
      isVice: pid === lineup.vice,
      isNew: view === "after" && !before.has(pid),
      isOut: view === "before" && sold.has(pid),
      note: view === "after" && replaces[pid] ? `for ${name(replaces[pid])}` : undefined,
      doubtful: p.doubtful,
      news: p.news,
      kit: kitFor(p, data.clubs),
      onSelect: () => info.open(p),
    };
  };

  const subtitle = [
    first.moves.length ? first.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ") : "Roll the transfer",
    first.chip ? CHIP_LABELS[first.chip] : plan.tag === "hit" ? `−${4 * first.hits} hit` : plan.tag === "free" ? "free transfer" : null,
    `captain ${name(first.captain)}`,
    `vice ${name(first.vice)}`,
  ].filter(Boolean).join(" · ");

  const h2h = plan.head_to_head;
  const later = plan.gameweeks.slice(1);

  return (
    <main className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <BackLink href={back} label="All plans" />
        <ThemeToggle />
      </div>

      <div className="flex flex-col gap-1">
        <h1 className="m-0 font-display text-2xl font-bold">
          {strategyLabel(data.strategy)} · Plan {plan.rank}
        </h1>
        <div className="text-[13px] text-text2">{subtitle}</div>
        {first.chip === "freehit" && (
          <div className="text-[12.5px] text-text3">A one-week Free Hit squad: your team comes back in GW{first.gw + 1}.</div>
        )}
      </div>

      <Why explanation={explanation} />

      <div className="flex items-center justify-between">
        <Segmented
          size="md"
          label="Squad view"
          value={view}
          onChange={setView}
          options={[
            { key: "before", label: "Before" },
            { key: "after", label: "After" },
          ]}
        />
        <div className="flex flex-col items-end gap-px">
          <div className="text-[11.5px] text-text3">GW{gw} projection</div>
          <div className="font-display text-xl font-bold">{pts(lineup.xpts)}</div>
        </div>
      </div>

      <Pitch players={lineup.starting.map(token)} positions={positions} order={order} />
      <Bench players={lineup.bench.map(token)} />

      {plan.threats.length > 0 && (
        <div className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-3.5">
          <div className="flex flex-col gap-0.5">
            <div className="font-display text-base font-bold">Rival threats</div>
            <div className="text-[12.5px] text-text3">Players your rivals start and you won&apos;t have. If they haul, you lose ground.</div>
          </div>
          {plan.threats.map((t) => {
            const p = data.players[t.player];
            const g = gwOf(p, gw);
            return (
              <div key={t.player} className="grid grid-cols-[minmax(0,1fr)_76px_52px] items-center gap-2 border-t border-line py-2">
                <div className="flex min-w-0 flex-col gap-px">
                  <div className="truncate text-sm font-semibold">{p.name}</div>
                  <div className="truncate text-[11.5px] text-text3">{p.club} · {p.position} · {g.fixture}</div>
                </div>
                <div className="text-[12.5px] font-semibold text-bad">Starts {t.rivals_starting}/{n}</div>
                <div className="text-right text-[12.5px]">{pts(t.xpts)} xP</div>
              </div>
            );
          })}
        </div>
      )}

      {h2h && (
        <div className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface p-3.5">
          <div className="flex flex-col gap-0.5">
            <div className="font-display text-base font-bold">Head-to-head vs {h2h.opponent_rank === 1 ? "1st" : h2h.points_gap > 0 ? "the manager above you" : "your nearest rival"}</div>
            <div className="text-[12.5px] text-text3">
              {h2h.opponent_name} · {h2h.opponent_entry_name} · {h2h.points_gap > 0 ? `${h2h.points_gap} pts ahead` : h2h.points_gap < 0 ? `${-h2h.points_gap} pts behind you` : "level on points"}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-0.5 rounded-[10px] bg-surface2 p-2.5">
              <div className="text-[11.5px] text-text3">You (GW{plan.after.gw})</div>
              <div className="font-display text-lg font-bold">{pts(h2h.you_xpts)}</div>
            </div>
            <div className="flex flex-col gap-0.5 rounded-[10px] bg-surface2 p-2.5">
              <div className="truncate text-[11.5px] text-text3">{h2h.opponent_name.split(" ")[0]} (GW{plan.after.gw})</div>
              <div className="font-display text-lg font-bold">{pts(h2h.them_xpts)}</div>
            </div>
          </div>
          <div className="text-[13px] leading-[1.45] text-text2">
            You share {h2h.shared_players} players. The week is decided by your {listNames(h2h.your_differentials.map(name))} against their{" "}
            {listNames(h2h.their_differentials.map(name))}, with {name(h2h.their_captain)} as their likely captain.
          </div>
        </div>
      )}

      {later.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface p-3.5">
          <div className="font-display text-base font-bold">Later in the plan</div>
          {later.map((g) => (
            <div key={g.gw} className="flex justify-between gap-3 border-t border-line pt-1.5 text-[13px]">
              <span className="text-text3">GW{g.gw}</span>
              <span className="text-right">
                {g.moves.length ? g.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ") : "No transfers"}
                {g.hits ? ` (−${4 * g.hits})` : ""} · C {name(g.captain)} · V {name(g.vice)}
                {g.chip ? ` · ${CHIP_LABELS[g.chip]}` : ""}
              </span>
            </div>
          ))}
        </div>
      )}

      <a
        href="https://fantasy.premierleague.com/transfers"
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => track("open_fpl_transfers", { rank: plan.rank })}
        className="flex h-12 shrink-0 items-center justify-center rounded-xl bg-accent text-[15px] font-semibold text-white no-underline"
      >
        Make this transfer in the FPL app
      </a>
      <div className="-mt-1.5 text-center text-xs text-text3">We can&apos;t make transfers for you.</div>
      <SharePlan plan={plan} data={data} className="flex h-11 items-center justify-center rounded-xl border border-line bg-surface" />
      <PlanFeedback context={{ page: "plan", strategy: data.strategy, horizon: data.horizon, rank: plan.rank, gw: first.gw }} />
      {info.sheet}
    </main>
  );
}

function listNames(names: string[]): string {
  if (names.length === 0) return "squad";
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
