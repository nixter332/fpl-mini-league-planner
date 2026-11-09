"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Bench, Pitch, kitFor, type PitchPlayer } from "@/components/Pitch";
import { Sheet } from "@/components/Sheet";
import { BackLink, ErrorBox, Loading, ThemeToggle, Tile } from "@/components/ui";
import { track } from "@/lib/analytics";
import { ApiError, decodeWhatIf, encodeWhatIf, getAllPlayers, getPlans, postWhatIf } from "@/lib/api";
import { getDraft, listDrafts, saveDraft, suggestName, type Draft } from "@/lib/drafts";
import { CHIP_LABELS, gwOf, money, pts, signed } from "@/lib/format";
import type { ChipName, Player, PlansResponse, PlayersResponse, Position, Strategy, WhatIfMove, WhatIfResponse, WhatIfSwap } from "@/lib/types";

export default function WhatIfPage() {
  return (
    <Suspense fallback={<Loading message="Loading your team…" />}>
      <WhatIf />
    </Suspense>
  );
}

function WhatIf() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const entry = Number(id);
  const leagueParam = search.get("league");
  const league = leagueParam === null ? null : Number(leagueParam);
  const strategyParam = search.get("strategy");
  const strategy: Strategy = strategyParam === "balanced" || strategyParam === "risky" ? strategyParam : "protect";
  const { moves, captains, chips, swaps } = decodeWhatIf(search);
  const draftId = search.get("draft");
  const key = search.toString();

  const [result, setResult] = useState<{ key: string; data: WhatIfResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState<PlayersResponse | null>(null);
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [gwIndex, setGwIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [lineupFor, setLineupFor] = useState<number | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [draftCount, setDraftCount] = useState(0);

  // Drafts live in this browser, so read them after the page loads.
  useEffect(() => {
    setDraft(draftId ? getDraft(draftId) : null);
    setDraftCount(listDrafts(entry).length);
  }, [draftId, entry]);

  useEffect(() => {
    let live = true;
    setError(null);
    postWhatIf({ team: entry, league, strategy, horizon: 4, moves, captains, chips, swaps })
      .then((data) => live && setResult({ key, data }))
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Couldn't score that plan."));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    getAllPlayers(entry, league).then(setAll).catch(() => {});
    getPlans({ team: entry, league, strategy, horizon: 4, hits: 0, wildcard: null, freehit: null, chips: true }).then(setPlans).catch(() => {});
  }, [entry, league, strategy]);

  const positions = useMemo(() => {
    const map: Record<number, Position> = {};
    if (all) for (const p of Object.values(all.players)) map[p.id] = p.position;
    return map;
  }, [all]);

  const data = result?.data ?? null;
  const stale = result !== null && result.key !== key; // a change is being scored
  const update = (next: { moves?: WhatIfMove[]; captains?: Record<number, number>; chips?: Record<number, ChipName>; swaps?: WhatIfSwap[] }) => {
    setHistory((h) => [...h, key]);
    router.replace(`/team/${entry}/what-if?${queryFor(next.moves ?? moves, next.captains ?? captains, next.chips ?? chips, draftId, next.swaps ?? swaps)}`);
  };
  function queryFor(m: WhatIfMove[], c: Record<number, number>, x: Record<number, ChipName>, id: string | null, s: WhatIfSwap[] = swaps): string {
    const q = new URLSearchParams(encodeWhatIf(m, c, x, s));
    if (league !== null) q.set("league", String(league));
    q.set("strategy", strategy);
    if (id) q.set("draft", id);
    return q.toString();
  }
  const save = (asNew: boolean) => {
    const saved = saveDraft({ id: asNew ? undefined : draft?.id, name: draftName, team: entry, league, strategy, moves, captains, chips, swaps });
    setSaving(false);
    if (!saved) {
      setSavedNote("Couldn't save: this browser isn't allowing storage (private mode?).");
      return;
    }
    track("draft_saved", { new: asNew || !draft, moves: moves.length, chip: Object.values(chips)[0] ?? null });
    setDraft(saved);
    setDraftCount(listDrafts(entry).length);
    setSavedNote(`Saved "${saved.name}".`);
    if (saved.id !== draftId) router.replace(`/team/${entry}/what-if?${queryFor(moves, captains, chips, saved.id)}`);
  };
  const undo = () => {
    const prev = history[history.length - 1];
    if (prev === undefined) return;
    setHistory((h) => h.slice(0, -1));
    router.replace(`/team/${entry}/what-if?${prev}`);
  };

  if (error && !data) return <ErrorBox message={error} action={<Link href={`/team/${entry}`}>Back to your team</Link>} />;
  if (!data || !all) return <Loading message="Loading your team…" />;

  const week = data.weeks[Math.min(gwIndex, data.weeks.length - 1)];
  const player = (pid: number): Player | undefined => all.players[pid];
  const name = (pid: number) => player(pid)?.name ?? `#${pid}`;
  const boughtNow = Object.fromEntries(week.moves.map((m) => [m.player_in, m.player_out]));
  // Spots come from the squad *before* this week's moves, so a new player takes the sold one's spot.
  const before = new Set(week.squad);
  for (const m of week.moves) {
    before.delete(m.player_in);
    before.add(m.player_out);
  }
  const order: Record<number, number> = Object.fromEntries([...before].sort((a, b) => a - b).map((pid, i) => [pid, i]));
  for (const [pin, pout] of Object.entries(boughtNow)) order[Number(pin)] = order[pout] ?? Number(pin);

  const token = (pid: number): PitchPlayer => {
    const p = player(pid);
    const g = p ? gwOf(p, week.gw) : { fixture: "—", xpts: 0 };
    return {
      id: pid,
      name: name(pid),
      info: g.fixture,
      value: pts(g.xpts),
      isCaptain: pid === week.captain,
      isVice: pid === week.vice,
      isNew: pid in boughtNow,
      note: boughtNow[pid] ? `for ${name(boughtNow[pid])}` : undefined,
      doubtful: p?.doubtful,
      news: p?.news,
      kit: p ? kitFor(p, all.clubs) : { body: "#94A0AF", sleeve: "#94A0AF", trim: "#FFFFFF" },
      onSelect: () => {
        setSelected(pid);
        setReplacing(false);
        setLineupFor(null);
      },
    };
  };

  const plan1 = plans?.plans[0];
  const weekChips = data.chips_left.filter((c) => c.start <= week.gw && week.gw <= c.stop);
  // "2 free · 1 used": the free transfers going into this week, and how many this week uses.
  const transfersText = week.chip === "wildcard" || week.chip === "freehit"
    ? `${CHIP_LABELS[week.chip]} · ${week.moves.length} used`
    : `${week.free_transfers} free · ${week.moves.length} used${week.hits ? ` (−${4 * week.hits})` : ""}`;

  return (
    <main className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <BackLink href={`/team/${entry}${league !== null ? `?league=${league}` : ""}`} label="My team" />
        <ThemeToggle />
      </div>
      <div className="flex flex-col gap-1">
        <h1 className="m-0 font-display text-[24px] font-bold">What-if{draft ? `: ${draft.name}` : ""}</h1>
        <div className="text-[13px] text-text2">Tap a player to transfer him, bench him or make him captain. Points update as you go.</div>
      </div>

      {error && <ErrorBox message={`${error} The numbers below are from before your last change.`} />}

      <div className={`flex flex-col gap-1 rounded-[14px] border border-cap-line bg-cap-bg px-3.5 py-3 ${stale ? "opacity-60" : ""}`} data-testid="whatif-total" aria-busy={stale}>
        <div className="text-[11.5px] font-semibold tracking-[0.4px] text-text3">
          YOUR PLAN · GW{data.gws[0]}–GW{data.gws[data.gws.length - 1]}
          {stale && !error ? " · updating…" : ""}
        </div>
        <div className="text-sm leading-[1.45]">
          <span className={`font-display text-lg font-bold ${data.xpts_gain >= 0 ? "text-good" : "text-bad"}`}>{signed(data.xpts_gain)}</span> xPts vs making no transfers
          {plan1 && (
            <>
              {" · "}the planner&apos;s Plan 1: <span className="font-semibold">{signed(plan1.xpts_gain)}</span>
              {plan1.chip_xpts ? <span className="text-text3"> (incl. chips {signed(plan1.chip_xpts)})</span> : null}
            </>
          )}
        </div>
        <div className="text-xs text-text3">Leaves {data.free_transfers_after} free transfer{data.free_transfers_after === 1 ? "" : "s"} for GW{data.gws[data.gws.length - 1] + 1}.</div>
      </div>

      {data.problems.length > 0 && (
        <ErrorBox message={data.problems.map((p) => p.message).join(" ")} />
      )}

      <div className="flex gap-1.5" role="group" aria-label="Gameweek">
        {data.weeks.map((w, i) => (
          <button
            key={w.gw}
            type="button"
            aria-pressed={i === gwIndex}
            onClick={() => setGwIndex(i)}
            className={`h-9 flex-1 rounded-[10px] border text-[13px] font-semibold ${i === gwIndex ? "border-chip-on-bg bg-chip-on-bg text-chip-on-text" : "border-line bg-surface text-text"}`}
          >
            GW{w.gw}
            {w.moves.length ? ` · ${w.moves.length}` : ""}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Tile label={`GW${week.gw} projection`} value={pts(week.xpts)} />
        <Tile label="Bank" value={money(week.bank)} />
        <Tile label="Transfers" value={transfersText} />
      </div>
      {week.own_lineup && (
        <div className="flex flex-wrap items-center gap-x-2 text-xs text-text2" data-testid="own-lineup">
          <span>
            Your lineup: <b>{pts(week.xpts)}</b> · best XI: {pts(week.best_xi_xpts)} ({signed(week.xpts - week.best_xi_xpts)})
          </span>
          <button
            type="button"
            onClick={() => update({ swaps: swaps.filter((s) => s.gw !== week.gw) })}
            className="font-semibold text-link"
          >
            Use best lineup
          </button>
        </div>
      )}

      <Pitch players={week.starting.map(token)} positions={positions} order={order} />
      <Bench players={week.bench.map(token)} />

      <div className="flex flex-wrap items-center gap-2">
        {weekChips.length > 0 && (
          <select
            aria-label="Chip"
            value={chips[week.gw] ?? ""}
            onChange={(e) => {
              const next = { ...chips };
              if (e.target.value) next[week.gw] = e.target.value as ChipName;
              else delete next[week.gw];
              track("what_if_chip", { chip: e.target.value || null });
              update({ chips: next });
            }}
            className="h-[30px] rounded-full border-0 bg-pill px-3 text-xs text-text2"
          >
            <option value="">No chip in GW{week.gw}</option>
            {weekChips.map((c) => (
              <option key={`${c.name}-${c.stop}`} value={c.name}>
                {c.label} in GW{week.gw}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() => {
            setDraftName(draft?.name ?? suggestName(moves, chips, listDrafts(entry)));
            setSaving(true);
            setSavedNote(null);
          }}
          className="h-[30px] rounded-full bg-accent px-3 text-xs font-semibold text-white"
        >
          {draft ? "Save draft…" : "Save as draft"}
        </button>
        <button type="button" onClick={undo} disabled={!history.length} className="h-[30px] rounded-full bg-pill px-3 text-xs font-semibold text-text2 disabled:opacity-40">
          Undo
        </button>
        <button
          type="button"
          onClick={() => update({ moves: [], captains: {}, chips: {} })}
          disabled={!moves.length && !Object.keys(captains).length && !Object.keys(chips).length}
          className="h-[30px] rounded-full bg-pill px-3 text-xs font-semibold text-text2 disabled:opacity-40"
        >
          Reset
        </button>
      </div>

      {savedNote && <div className="text-xs text-text2" role="status">{savedNote}</div>}
      <Link href={`/team/${entry}/drafts${league !== null ? `?league=${league}` : ""}`} className="self-start text-[13px] font-semibold no-underline" data-testid="my-drafts-link">
        My drafts{draftCount ? ` (${draftCount})` : ""} →
      </Link>

      {saving && (
        <Sheet title={draft ? "Save draft" : "Save as draft"} onClose={() => setSaving(false)}>
          <label className="flex flex-col gap-1 text-[13px] text-text2">
            Name
            <input
              value={draftName}
              maxLength={60}
              onChange={(e) => setDraftName(e.target.value)}
              aria-label="Draft name"
              className="h-10 rounded-lg border border-input-line bg-input px-3 text-sm text-text"
            />
          </label>
          <div className="text-xs text-text3">Saved on this device. It keeps your transfers, captains and chips; the points are recalculated each time you open it.</div>
          <div className="flex gap-2">
            <button type="button" onClick={() => save(false)} className="h-11 flex-1 rounded-xl bg-accent text-sm font-semibold text-white">
              {draft ? "Save changes" : "Save"}
            </button>
            {draft && (
              <button type="button" onClick={() => save(true)} className="h-11 flex-1 rounded-xl border border-line bg-surface text-sm font-semibold">
                Save as new
              </button>
            )}
          </div>
        </Sheet>
      )}

      {moves.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface p-3.5" data-testid="whatif-moves">
          <div className="font-display text-base font-bold">Your transfers</div>
          {moves.map((m, i) => (
            <div key={`${m.gw}-${m.out}-${m.into}`} className="flex items-center justify-between gap-2 border-t border-line pt-1.5 text-[13px]">
              <span>
                <span className="text-text3">GW{m.gw}</span> {name(m.out)} → {name(m.into)}
              </span>
              <button type="button" onClick={() => update({ moves: moves.filter((_, j) => j !== i) })} aria-label={`Remove ${name(m.out)} to ${name(m.into)}`} className="text-xs text-text3 underline">
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {plan1 && (
        <Link href={`/plans?team=${entry}&league=${league ?? 0}&strategy=${strategy}&horizon=4&hits=0`} className="self-center text-[13px] font-semibold no-underline">
          See the planner&apos;s plans →
        </Link>
      )}

      {selected !== null && (
        <Sheet title={name(selected)} onClose={() => { setSelected(null); setLineupFor(null); }}>
          {lineupFor !== null ? (
            <LineupPicker
              all={all}
              selected={selected}
              options={(week.starting.includes(selected) ? week.bench : week.starting).filter(
                (p) => (all.players[p]?.position === "GKP") === (all.players[selected]?.position === "GKP"),
              )}
              gw={week.gw}
              starting={week.starting.includes(selected)}
              onPick={(other) => {
                const benching = week.starting.includes(selected);
                track("what_if_lineup", { gw: week.gw });
                update({ swaps: [...swaps, { gw: week.gw, bench: benching ? selected : other, start: benching ? other : selected }] });
                setSelected(null);
                setLineupFor(null);
              }}
            />
          ) : !replacing ? (
            <PlayerActions
              p={player(selected)}
              gw={week.gw}
              inXi={week.starting.includes(selected)}
              isCaptain={week.captain === selected}
              boughtFor={boughtNow[selected] ? name(boughtNow[selected]) : null}
              onTransfer={() => setReplacing(true)}
              onLineup={() => setLineupFor(selected)}
              onBench={week.bench.includes(selected)}
              onCaptain={() => {
                track("what_if_captain");
                update({ captains: { ...captains, [week.gw]: selected } });
                setSelected(null);
              }}
              onUndoBuy={() => {
                update({ moves: moves.filter((m) => !(m.gw === week.gw && m.into === selected)) });
                setSelected(null);
              }}
            />
          ) : (
            <ReplacementPicker
              all={all}
              out={selected}
              squad={week.squad}
              budget={(player(selected)?.sell_price ?? player(selected)?.price ?? 0) + week.bank}
              gws={data.gws.filter((g) => g >= week.gw)}
              onPick={(into) => {
                track("what_if_transfer", { gw: week.gw });
                update({ moves: [...moves, { gw: week.gw, out: selected, into }] });
                setSelected(null);
              }}
            />
          )}
        </Sheet>
      )}
    </main>
  );
}

function PlayerActions({
  p, gw, inXi, isCaptain, boughtFor, onTransfer, onCaptain, onUndoBuy, onLineup, onBench,
}: {
  p?: Player; gw: number; inXi: boolean; isCaptain: boolean; boughtFor: string | null;
  onTransfer: () => void; onCaptain: () => void; onUndoBuy: () => void; onLineup: () => void; onBench: boolean;
}) {
  if (!p) return null;
  return (
    <>
      <div className="text-[13px] text-text2">
        {p.club} · {p.position} · {money(p.sell_price ?? p.price)}
      </div>
      {p.news && <div className="rounded-lg bg-warn-bg px-3 py-2 text-[12.5px] text-warn-text">{p.news}</div>}
      <div className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1 text-[13px]">
        {p.gws.filter((g) => g.gw >= gw).slice(0, 4).map((g) => (
          <div key={g.gw} className="contents">
            <span className="text-text3">GW{g.gw}</span>
            <span className="truncate">{g.fixture}</span>
            <span className="text-right font-semibold">{pts(g.xpts)}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {boughtFor ? (
          <button type="button" onClick={onUndoBuy} className="h-11 rounded-xl border border-line bg-surface text-sm font-semibold">
            Undo: bring back {boughtFor}
          </button>
        ) : (
          <button type="button" onClick={onTransfer} className="h-11 rounded-xl bg-accent text-sm font-semibold text-white">
            Transfer out in GW{gw}
          </button>
        )}
        {inXi && !isCaptain && (
          <button type="button" onClick={onCaptain} className="h-11 rounded-xl border border-line bg-surface text-sm font-semibold">
            Make captain in GW{gw}
          </button>
        )}
        <button type="button" onClick={onLineup} className="h-11 rounded-xl border border-line bg-surface text-sm font-semibold">
          {onBench ? `Bring on in GW${gw}` : `Move to bench in GW${gw}`}
        </button>
      </div>
    </>
  );
}

function ReplacementPicker({
  all, out, squad, budget, gws, onPick,
}: {
  all: PlayersResponse; out: number; squad: number[]; budget: number; gws: number[]; onPick: (into: number) => void;
}) {
  const [query, setQuery] = useState("");
  const me = all.players[out];
  const owned = new Set(squad);
  const total = (p: Player) => p.gws.filter((g) => gws.includes(g.gw)).reduce((s, g) => s + g.xpts, 0);
  const list = Object.values(all.players)
    .filter((p) => p.position === me.position && !owned.has(p.id))
    .filter((p) => !query.trim() || `${p.name} ${p.club}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => total(b) - total(a))
    .slice(0, 40);
  return (
    <>
      <div className="text-[13px] text-text2">
        Replacing {me.name}: {money(budget)} to spend. Sorted by projected points, GW{gws[0]}–GW{gws[gws.length - 1]} ({pts(total(me))} for {me.name}).
      </div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search name or club"
        aria-label="Search players"
        className="h-10 rounded-lg border border-input-line bg-input px-3 text-sm text-text placeholder:text-text3"
      />
      <div className="flex flex-col gap-1.5" data-testid="replacement-picker">
        {list.map((p) => {
          const short = p.price - budget;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onPick(p.id)}
              className={`flex items-center justify-between gap-2 rounded-xl border border-line px-3 py-2 text-left ${short > 0 ? "opacity-50" : "bg-surface"}`}
            >
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-semibold">{p.name}</span>
                <span className="truncate text-[11.5px] text-text3">
                  {p.club} · {money(p.price)} · {gwOf(p, gws[0]).fixture}
                  {short > 0 ? ` · ${money(short)} short` : ""}
                </span>
              </span>
              <span className="shrink-0 text-sm font-bold">{pts(total(p))}</span>
            </button>
          );
        })}
      </div>
    </>
  );
}

function LineupPicker({
  all, selected, options, gw, starting, onPick,
}: {
  all: PlayersResponse; selected: number; options: number[]; gw: number; starting: boolean; onPick: (other: number) => void;
}) {
  const me = all.players[selected];
  const x = (pid: number) => all.players[pid]?.gws.find((g) => g.gw === gw);
  return (
    <>
      <div className="text-[13px] text-text2">
        {starting ? `Bench ${me.name} in GW${gw}. Who comes on?` : `Start ${me.name} in GW${gw}. Who goes to the bench?`} Formations must
        keep 1 goalkeeper, at least 3 defenders, 2 midfielders and 1 forward.
      </div>
      <div className="flex flex-col gap-1.5" data-testid="lineup-picker">
        {options.map((pid) => (
          <button key={pid} type="button" onClick={() => onPick(pid)} className="flex items-center justify-between gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-left">
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-semibold">{all.players[pid]?.name}</span>
              <span className="truncate text-[11.5px] text-text3">{all.players[pid]?.position} · {x(pid)?.fixture}</span>
            </span>
            <span className="shrink-0 text-sm font-bold">{pts(x(pid)?.xpts ?? 0)}</span>
          </button>
        ))}
      </div>
    </>
  );
}
