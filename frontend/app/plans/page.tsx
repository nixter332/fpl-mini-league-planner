"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { BackLink, ErrorBox, Facts, Loading, ThemeToggle } from "@/components/ui";
import { Why, useExplanation } from "@/components/Why";
import { ApiError, getPlans, planQuery, readPlanParams, waitForRivals, type PlanParams } from "@/lib/api";
import { STRATEGIES, money, signed } from "@/lib/format";
import type { Plan, PlansResponse, RivalsProgress, Strategy } from "@/lib/types";

export default function PlansPage() {
  return (
    <Suspense fallback={<Loading message="Building your plans…" />}>
      <PlansScreen />
    </Suspense>
  );
}

function PlansScreen() {
  const router = useRouter();
  const search = useSearchParams();
  const params = readPlanParams(search);
  const key = planQuery(params);
  const [data, setData] = useState<PlansResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rivals, setRivals] = useState<RivalsProgress | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    // Plans need every rival's squad; wait for the background load first so we can show progress.
    waitForRivals(params.team, params.league, (p) => live && setRivals(p), () => live)
      .then(() => getPlans(params))
      .then((d) => {
        if (!live) return;
        setData(d);
        // Warm the other strategies so the dial switches instantly.
        for (const s of STRATEGIES) if (s.key !== params.strategy) getPlans({ ...params, strategy: s.key }).catch(() => {});
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Couldn't build plans."));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const go = (patch: Partial<PlanParams>) => {
    const next = { ...params, ...patch };
    const q = new URLSearchParams({ team: String(next.team), strategy: next.strategy, horizon: String(next.horizon), hits: String(next.hits) });
    if (next.league !== null) q.set("league", String(next.league));
    router.replace(`/plans?${q}`);
  };

  const teamHref = `/team/${params.team}${params.league !== null ? `?league=${params.league}` : ""}`;
  const current = data && planQuery({ ...params }) === key && data.strategy === params.strategy && data.horizon === params.horizon && data.max_hits === params.hits ? data : null;
  const strategy = STRATEGIES.find((s) => s.key === params.strategy)!;
  const gap = data?.standing?.gap_to_first ?? null;

  return (
    <main className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <BackLink href={teamHref} label="My team" />
        <ThemeToggle />
      </div>

      <div className="flex flex-col gap-1">
        <h1 className="m-0 font-display text-[26px] font-bold">Transfer plans{current ? ` · GW${current.gws[0]}` : ""}</h1>
        {current && (
          <div className="text-[13px] text-text2">
            {current.free_transfers} free transfer{current.free_transfers === 1 ? "" : "s"} · {money(current.bank)} in the bank · planned over the next {current.horizon} GW
            {current.horizon === 1 ? "" : "s"}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface p-3.5">
        <div className="flex items-baseline justify-between gap-2">
          <div className="text-[13px] font-semibold">Strategy</div>
          {gap !== null && (
            <div className={`text-xs font-semibold ${gap > 0 ? "text-bad" : "text-good"}`}>
              {gap > 0 ? `You're ${gap} pts behind 1st` : "You're top of the league"}
            </div>
          )}
        </div>
        <div className="flex gap-1 rounded-xl bg-seg p-1" role="group" aria-label="Strategy">
          {STRATEGIES.map((s) => (
            <button
              key={s.key}
              type="button"
              aria-pressed={s.key === params.strategy}
              onClick={() => go({ strategy: s.key as Strategy })}
              className={`min-h-10 flex-1 rounded-[9px] text-[13px] font-semibold ${s.key === params.strategy ? "bg-accent text-white" : "bg-transparent text-text2"}`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="text-[13px] leading-[1.45] text-text2">{strategy.desc}</div>
        <div className="flex flex-wrap gap-1.5">
          <PillSelect
            label="Horizon"
            value={params.horizon}
            options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `Horizon: ${n} GW${n === 1 ? "" : "s"}` }))}
            onChange={(n) => go({ horizon: n })}
          />
          <PillSelect
            label="Max hits"
            value={params.hits}
            options={[0, 1, 2, 3].map((n) => ({ value: n, label: `Max hits: ${n} over ${params.horizon} GW${params.horizon === 1 ? "" : "s"}` }))}
            onChange={(n) => go({ hits: n })}
          />
          {data?.standing && (
            <span className="rounded-full bg-pill px-2.5 py-[5px] text-xs text-text2">
              Rivals: {data.standing.league.name} ({data.standing.n_rivals})
            </span>
          )}
        </div>
      </div>

      {error && <ErrorBox message={error} />}
      {!current && !error && (
        <Loading
          message={
            rivals && !rivals.ready
              ? `Loading your rivals' teams: ${rivals.loaded} of ${rivals.total}…`
              : "Building your plans. This takes a few seconds…"
          }
        />
      )}

      {current && (
        <>
          <div className="flex flex-col gap-[3px] rounded-[14px] border border-cap-line bg-cap-bg px-3.5 py-3">
            <div className="text-[11.5px] font-semibold tracking-[0.4px] text-text3">CAPTAIN</div>
            <div className="text-sm leading-[1.4]">{current.captain_note}</div>
          </div>
          {current.plans.map((plan) => (
            <PlanCard key={plan.rank} plan={plan} data={current} params={params} href={`/plans/${plan.rank}?${search.toString()}`} />
          ))}
          <div className="text-center text-xs text-text3">The solver picks the transfers. AI only writes the reasons.</div>
          <Facts facts={current.facts} />
        </>
      )}
    </main>
  );
}

function PillSelect({ label, value, options, onChange }: { label: string; value: number; options: { value: number; label: string }[]; onChange: (n: number) => void }) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="h-[26px] appearance-none rounded-full border-0 bg-pill px-2.5 text-xs text-text2"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

const TAGS = {
  free: { label: "Free transfer", cls: "bg-free-bg text-free-text" },
  hit: { label: "−4 hit", cls: "bg-hit-bg text-hit-text" },
  roll: { label: "Roll transfer", cls: "bg-roll-bg text-roll-text" },
};

function PlanCard({ plan, data, params, href }: { plan: Plan; data: PlansResponse; params: PlanParams; href: string }) {
  const explanation = useExplanation(params, plan.rank);
  const first = plan.gameweeks[0];
  const n = data.standing?.n_rivals ?? 0;
  const tag = TAGS[plan.tag];
  const later = plan.gameweeks.slice(1).filter((g) => g.moves.length);
  const name = (id: number) => data.players[id]?.name ?? `#${id}`;
  const meta = (id: number, price: number) => {
    const p = data.players[id];
    return `${p.club} · ${money(price)}${n ? ` · own ${p.rivals_owned}/${n}` : ""}`;
  };
  return (
    <div
      data-testid="plan-card"
      className={`flex flex-col gap-2.5 rounded-2xl bg-surface p-3.5 ${plan.rank === 1 ? "border-2 border-accent" : "border border-line"}`}
    >
      <div className="flex items-center justify-between">
        <div className="font-display text-base font-bold">{plan.rank === 1 ? "Plan 1 · Recommended" : `Plan ${plan.rank}`}</div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tag.cls}`}>{plan.tag === "hit" && plan.hits > 1 ? `−${4 * plan.hits} hits` : tag.label}</span>
      </div>

      {first.moves.length ? (
        <div className="flex flex-col gap-1.5">
          {first.moves.map((m) => (
            <div key={m.player_out} className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] items-center gap-1 rounded-[10px] bg-surface2 px-2.5 py-2">
              <div className="flex min-w-0 flex-col gap-px">
                <div className="text-[11px] font-semibold text-out">OUT</div>
                <div className="truncate text-sm font-semibold">{name(m.player_out)}</div>
                <div className="truncate text-[11.5px] text-text3">{meta(m.player_out, m.out_price)}</div>
              </div>
              <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="var(--text3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
              <div className="flex min-w-0 flex-col gap-px">
                <div className="text-[11px] font-semibold text-good">IN</div>
                <div className="truncate text-sm font-semibold">{name(m.player_in)}</div>
                <div className="truncate text-[11.5px] text-text3">{meta(m.player_in, m.in_price)}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[10px] bg-surface2 p-3 text-sm font-semibold">{plan.summary}</div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-px">
          <div className="text-[11.5px] text-text3">Expected points gained ({data.horizon} GW{data.horizon === 1 ? "" : "s"})</div>
          <div className="font-display text-lg font-bold">{signed(plan.xpts_gain)}</div>
        </div>
        <div className="flex flex-col gap-px">
          <div className="text-[11.5px] text-text3" title="Expected points from players your rivals won't also get">Differential points gained</div>
          <div className="font-display text-lg font-bold text-good">{n ? signed(plan.differential_gain) : "—"}</div>
        </div>
      </div>

      <Why explanation={explanation} />

      <div className="flex flex-col gap-1 rounded-[10px] bg-surface2 px-3 py-2.5">
        <div className="text-xs font-semibold text-text3">In numbers</div>
        <div className="text-[13px] leading-[1.45]">
          {plan.is_roll ? `${signed(plan.xpts_gain)} xPts over ${data.horizon} GWs vs making no transfers.` : plan.summary} Captain {name(first.captain)} in GW{first.gw}.
          {later.length > 0 && (
            <>
              {" "}Then:{" "}
              {later.map((g, i) => (
                <span key={g.gw}>
                  GW{g.gw} {g.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ")}
                  {g.hits ? ` (−${4 * g.hits})` : ""}
                  {i < later.length - 1 ? "; " : "."}
                </span>
              ))}
            </>
          )}
        </div>
        {!plan.proven_optimal && <div className="text-[11.5px] text-text3">Best plan found within the time limit.</div>}
      </div>

      <Link href={href} className="flex min-h-8 items-center text-sm font-semibold no-underline">View on pitch →</Link>
    </div>
  );
}
