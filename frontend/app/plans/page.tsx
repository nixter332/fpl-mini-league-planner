"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { BackLink, ErrorBox, Facts, Loading, ThemeToggle } from "@/components/ui";
import { Why, useExplanation } from "@/components/Why";
import { FeedbackLink, PlanFeedback } from "@/components/Feedback";
import { Countdown } from "@/components/Countdown";
import { SharePlan } from "@/components/SharePlan";
import { PriceMove } from "@/components/PriceMove";
import { track } from "@/lib/analytics";
import { rememberNav } from "@/lib/nav";
import { ApiError, getPlans, pageQuery, planQuery, readPlanParams, waitForRivals, type PlanParams } from "@/lib/api";
import { CHIP_LABELS, STRATEGIES, money, signed } from "@/lib/format";
import type { ChipName, Plan, PlansResponse, RivalsProgress, Strategy } from "@/lib/types";

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
  const [loaded, setLoaded] = useState<{ key: string; data: PlansResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rivals, setRivals] = useState<RivalsProgress | null>(null);
  const [open, setOpen] = useState(1); // the plan shown in full; the others are one-line rows
  const [showSettings, setShowSettings] = useState(false);
  const data = loaded?.data ?? null;

  useEffect(() => {
    let live = true;
    setError(null);
    setOpen(1);
    // Plans need every rival's squad; wait for the background load first so we can show progress.
    waitForRivals(params.team, params.league, (p) => live && setRivals(p), () => live)
      .then(() => getPlans(params))
      .then((d) => {
        if (!live) return;
        setLoaded({ key, data: d });
        rememberNav({ team: params.team, league: d.standing?.league.id ?? params.league ?? 0, strategy: params.strategy });
        track("plans_loaded", {
          strategy: params.strategy, horizon: params.horizon, hits: params.hits, chips: params.chips,
          wildcard: params.wildcard !== null, freehit: params.freehit !== null, plans: d.plans.length,
          plan1_chip: d.plans[0]?.gameweeks.find((g) => g.chip)?.chip ?? null,
        });
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
    for (const [setting, value] of Object.entries(patch)) track("plan_setting_changed", { setting, value: value as string | number | boolean | null });
    router.replace(`/plans?${pageQuery({ ...params, ...patch })}`);
  };

  const teamHref = `/team/${params.team}${params.league !== null ? `?league=${params.league}` : ""}`;
  const current = loaded?.key === key ? loaded.data : null;
  // Chip choices: only chips you still have, in GWs of this plan.
  const gws = data?.gws ?? [];
  const chipGws = (name: ChipName) =>
    gws.filter((g) => (data?.chips_left ?? []).some((c) => c.name === name && c.start <= g && g <= c.stop));
  const hasAuto = (data?.chips_left ?? []).some((c) => (c.name === "bboost" || c.name === "3xc") && gws.some((g) => c.start <= g && g <= c.stop));
  const strategy = STRATEGIES.find((s) => s.key === params.strategy)!;
  const gap = data?.standing?.gap_to_first ?? null;

  const plural = (n: number) => (n === 1 ? "" : "s");
  const settingsSummary = [
    `${params.horizon} GW${plural(params.horizon)}`,
    params.hits ? `up to ${params.hits} hit${plural(params.hits)}` : "no hits",
    params.wildcard !== null ? `Wildcard GW${params.wildcard}` : null,
    params.freehit !== null ? `Free Hit GW${params.freehit}` : null,
    hasAuto ? `Bench Boost / Triple Captain: ${params.chips ? "planner decides" : "off"}` : null,
  ].filter(Boolean).join(" · ");
  const openRank = current?.plans.some((p) => p.rank === open) ? open : current?.plans[0]?.rank;

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
            {current.free_transfers} free transfer{plural(current.free_transfers)} · {money(current.bank)} in the bank
          </div>
        )}
      </div>
      {current?.deadline && <Countdown gw={current.gws[0]} deadline={current.deadline} />}

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
        <button
          type="button"
          aria-expanded={showSettings}
          onClick={() => setShowSettings((v) => !v)}
          data-testid="plan-settings"
          className="flex items-center justify-between gap-2 border-t border-line pt-2.5 text-left"
        >
          <span className="min-w-0 text-xs leading-[1.4] text-text2">
            <span className="font-semibold text-text">Settings</span> · {settingsSummary}
          </span>
          <Chevron up={showSettings} />
        </button>
        {showSettings && (
          <>
            <div className="flex flex-wrap gap-1.5">
              <PillSelect
                label="Horizon"
                value={params.horizon}
                options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `Plan ahead: ${n} GW${plural(n)}` }))}
                onChange={(n) => go({ horizon: n })}
              />
              <PillSelect
                label="Max hits"
                value={params.hits}
                options={[0, 1, 2, 3].map((n) => ({ value: n, label: `Max hits: ${n} over ${params.horizon} GW${plural(params.horizon)}` }))}
                onChange={(n) => go({ hits: n })}
              />
              {data?.standing && (
                <span className="rounded-full bg-pill px-2.5 py-[5px] text-xs text-text2">
                  Rivals: {data.standing.league.name} ({data.standing.n_rivals})
                </span>
              )}
            </div>
            {(chipGws("wildcard").length > 0 || chipGws("freehit").length > 0 || hasAuto) && (
              <div className="flex flex-wrap gap-1.5" data-testid="chip-controls">
                {(["wildcard", "freehit"] as const).map((name) =>
                  chipGws(name).length > 0 ? (
                    <PillSelect
                      key={name}
                      label={CHIP_LABELS[name]}
                      value={params[name] ?? 0}
                      options={[
                        { value: 0, label: `${CHIP_LABELS[name]}: not playing` },
                        ...chipGws(name)
                          .filter((g) => g !== (name === "wildcard" ? params.freehit : params.wildcard))
                          .map((g) => ({ value: g, label: `${CHIP_LABELS[name]}: GW${g}` })),
                      ]}
                      onChange={(g) => go({ [name]: g || null })}
                    />
                  ) : null,
                )}
                {hasAuto && (
                  <PillSelect
                    label="Bench Boost and Triple Captain"
                    value={params.chips ? 1 : 0}
                    options={[
                      { value: 1, label: "Bench Boost / Triple Captain: planner decides" },
                      { value: 0, label: "Bench Boost / Triple Captain: don't play" },
                    ]}
                    onChange={(v) => go({ chips: v === 1 })}
                  />
                )}
              </div>
            )}
          </>
        )}
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
          {current.plans.map((plan) =>
            plan.rank === openRank ? (
              <PlanCard key={plan.rank} plan={plan} data={current} params={params} href={`/plans/${plan.rank}?${search.toString()}`} />
            ) : (
              <PlanRow
                key={plan.rank}
                plan={plan}
                data={current}
                onOpen={() => {
                  setOpen(plan.rank);
                  track("plan_opened", { rank: plan.rank });
                }}
              />
            ),
          )}
          <div className="text-center text-xs text-text3">The solver picks the transfers. AI only writes the reasons.</div>
          <Facts facts={current.facts} />
          <FeedbackLink context={{ page: "plans", strategy: current.strategy, horizon: current.horizon, gw: current.gws[0] }} />
        </>
      )}
    </main>
  );
}

function Chevron({ up }: { up: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className={`shrink-0 transition-transform ${up ? "rotate-180" : ""}`}>
      <path d="M4 6l4 4 4-4" fill="none" stroke="var(--text3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
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

const planTitle = (plan: Plan) => (plan.rank === 1 ? "Plan 1 · Recommended" : `Plan ${plan.rank}`);

/** A plan that isn't open: one row with this week's moves and the gain. Tap to open it. */
function PlanRow({ plan, data, onOpen }: { plan: Plan; data: PlansResponse; onOpen: () => void }) {
  const first = plan.gameweeks[0];
  const name = (id: number) => data.players[id]?.name ?? `#${id}`;
  const moves = first.moves.length ? first.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ") : "Roll the transfer";
  const chips = plan.gameweeks.filter((g) => g.chip).map((g) => `${CHIP_LABELS[g.chip!]} GW${g.gw}`);
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="plan-row"
      aria-label={`Open ${planTitle(plan)}`}
      className={`flex items-center justify-between gap-3 rounded-2xl bg-surface px-3.5 py-3 text-left ${plan.rank === 1 ? "border-2 border-accent" : "border border-line"}`}
    >
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="font-display text-[14px] font-bold">{planTitle(plan)}</span>
        <span className="text-[12.5px] leading-[1.4] text-text2">
          {moves}
          {chips.length ? ` · ${chips.join(", ")}` : ""}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5">
        <span className="font-display text-[15px] font-bold">{signed(plan.xpts_gain)}</span>
        <Chevron up={false} />
      </span>
    </button>
  );
}

function PlanCard({ plan, data, params, href }: { plan: Plan; data: PlansResponse; params: PlanParams; href: string }) {
  const explanation = useExplanation(params, plan.rank);
  const [details, setDetails] = useState(false);
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
        <div className="font-display text-base font-bold">{planTitle(plan)}</div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tag.cls}`}>{plan.tag === "hit" && plan.hits > 1 ? `−${4 * plan.hits} hits` : tag.label}</span>
      </div>
      {plan.gameweeks.some((g) => g.chip) && (
        <div className="flex flex-wrap gap-1.5" data-testid="plan-chips">
          {plan.gameweeks.filter((g) => g.chip).map((g) => (
            <span key={g.gw} className="rounded-full bg-cap-bg px-2.5 py-1 text-xs font-semibold text-why-label">
              {CHIP_LABELS[g.chip!]} · GW{g.gw}{g.chip_xpts ? ` · ${signed(g.chip_xpts)}` : ""}
            </span>
          ))}
        </div>
      )}

      {first.chip === "freehit" && (
        <div className="text-[12.5px] leading-[1.4] text-text2">
          Free Hit squad for GW{first.gw} only. Your team comes back in GW{first.gw + 1}.
        </div>
      )}
      {first.moves.length ? (
        <div className="flex flex-col gap-1.5">
          {first.moves.map((m) => (
            <div key={m.player_out} className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] items-center gap-1 rounded-[10px] bg-surface2 px-2.5 py-2">
              <div className="flex min-w-0 flex-col gap-px">
                <div className="text-[11px] font-semibold text-out">OUT</div>
                <div className="truncate text-sm font-semibold">{name(m.player_out)}<PriceMove change={data.players[m.player_out]?.price_change} /></div>
                <div className="truncate text-[11.5px] text-text3">{meta(m.player_out, m.out_price)}</div>
              </div>
              <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="var(--text3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
              <div className="flex min-w-0 flex-col gap-px">
                <div className="text-[11px] font-semibold text-good">IN</div>
                <div className="truncate text-sm font-semibold">{name(m.player_in)}<PriceMove change={data.players[m.player_in]?.price_change} /></div>
                <div className="truncate text-[11.5px] text-text3">{meta(m.player_in, m.in_price)}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[10px] bg-surface2 p-3 text-sm font-semibold">{plan.summary}</div>
      )}

      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[12.5px] text-text3">Expected points gained over {data.horizon} GW{data.horizon === 1 ? "" : "s"}</div>
        <div className="font-display text-xl font-bold">{signed(plan.xpts_gain)}</div>
      </div>

      <div className="text-[13px] leading-[1.45]" data-testid="plan-captain">
        <span className="font-semibold">Captain:</span>{" "}
        {plan.rank === 1 && data.captain_note ? data.captain_note : `${name(first.captain)} in GW${first.gw}.`} Vice: {name(first.vice)}.
      </div>

      <Why explanation={explanation} />

      <button
        type="button"
        aria-expanded={details}
        onClick={() => setDetails((v) => !v)}
        data-testid="plan-more"
        className="flex items-center gap-1 self-start text-[13px] font-semibold text-text2"
      >
        {details ? "Fewer details" : "More details"}
        <Chevron up={details} />
      </button>
      {details && (
        <div className="flex flex-col gap-2 rounded-[10px] bg-surface2 px-3 py-2.5" data-testid="plan-details">
          {n > 0 && (
            <div className="flex items-baseline justify-between gap-3">
              <div className="text-[12.5px] text-text3">Differential points gained (points your rivals won&apos;t also get)</div>
              <div className="font-display text-base font-bold text-good">{signed(plan.differential_gain)}</div>
            </div>
          )}
          <div className="text-[13px] leading-[1.45]">
            {plan.is_roll ? `${signed(plan.xpts_gain)} xPts over ${data.horizon} GWs vs making no transfers.` : plan.summary}
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
      )}

      <div className="flex items-center justify-between">
        <Link href={href} className="flex min-h-8 items-center text-sm font-semibold no-underline">View on pitch →</Link>
        <SharePlan plan={plan} data={data} className="min-h-8 px-1" />
      </div>
      <PlanFeedback context={{ page: "plans", strategy: data.strategy, horizon: data.horizon, rank: plan.rank, gw: data.gws[0] }} />
    </div>
  );
}
