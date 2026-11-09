"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Sheet } from "@/components/Sheet";
import { BackLink, Loading, ThemeToggle } from "@/components/ui";
import { track } from "@/lib/analytics";
import { encodeWhatIf, postWhatIf } from "@/lib/api";
import { deleteDraft, listDrafts, renameDraft, type Draft } from "@/lib/drafts";
import { CHIP_LABELS, money, pts, signed } from "@/lib/format";
import type { WhatIfResponse } from "@/lib/types";

const MAX_COMPARE = 3;

export default function DraftsPage() {
  return (
    <Suspense fallback={<Loading message="Loading your drafts…" />}>
      <Drafts />
    </Suspense>
  );
}

function Drafts() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const entry = Number(id);
  const league = search.get("league");

  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [scores, setScores] = useState<Record<string, WhatIfResponse | "error">>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [renaming, setRenaming] = useState<Draft | null>(null);
  const [newName, setNewName] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const reload = () => setDrafts(listDrafts(entry));
  useEffect(reload, [entry]);

  // Each draft is re-scored with today's projections, so numbers stay current.
  useEffect(() => {
    if (!drafts) return;
    let live = true;
    for (const d of drafts) {
      if (scores[d.id]) continue;
      postWhatIf({ team: d.team, league: d.league, strategy: d.strategy, horizon: 4, moves: d.moves, captains: d.captains, chips: d.chips })
        .then((r) => live && setScores((s) => ({ ...s, [d.id]: r })))
        .catch(() => live && setScores((s) => ({ ...s, [d.id]: "error" })));
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts]);

  if (!drafts) return <Loading message="Loading your drafts…" />;

  const openHref = (d: Draft) => {
    const q = new URLSearchParams(encodeWhatIf(d.moves, d.captains, d.chips));
    if (d.league !== null) q.set("league", String(d.league));
    q.set("strategy", d.strategy);
    q.set("draft", d.id);
    return `/team/${entry}/what-if?${q}`;
  };
  const toggle = (did: string) =>
    setSelected((s) => (s.includes(did) ? s.filter((x) => x !== did) : s.length < MAX_COMPARE ? [...s, did] : s));
  const compared = selected.map((did) => drafts.find((d) => d.id === did)).filter((d): d is Draft => !!d);

  return (
    <main className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <BackLink href={`/team/${entry}${league !== null ? `?league=${league}` : ""}`} label="My team" />
        <ThemeToggle />
      </div>
      <div className="flex flex-col gap-1">
        <h1 className="m-0 font-display text-[24px] font-bold">My drafts</h1>
        <div className="text-[13px] text-text2">Saved on this device. Points are recalculated with the latest projections. Tick up to {MAX_COMPARE} to compare.</div>
      </div>

      {drafts.length === 0 && (
        <div className="rounded-2xl border border-line bg-surface p-4 text-[13px] text-text2" data-testid="no-drafts">
          No drafts yet. Make transfers in{" "}
          <Link href={`/team/${entry}/what-if${league !== null ? `?league=${league}` : ""}`}>what-if</Link> and tap <b>Save as draft</b>.
        </div>
      )}

      <div className="flex flex-col gap-2" data-testid="draft-list">
        {drafts.map((d) => {
          const sc = scores[d.id];
          const chip = Object.entries(d.chips)[0];
          return (
            <div key={d.id} className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-3" data-testid="draft">
              <div className="flex items-start justify-between gap-2">
                <label className="flex min-w-0 items-start gap-2">
                  <input
                    type="checkbox"
                    checked={selected.includes(d.id)}
                    onChange={() => toggle(d.id)}
                    disabled={!selected.includes(d.id) && selected.length >= MAX_COMPARE}
                    aria-label={`Compare ${d.name}`}
                    className="mt-1"
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-sm font-semibold">{d.name}</span>
                    <span className="text-[11.5px] text-text3">
                      {d.moves.length} transfer{d.moves.length === 1 ? "" : "s"}
                      {chip ? ` · ${CHIP_LABELS[chip[1]]} GW${chip[0]}` : ""} · saved {new Date(d.updatedAt).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                    </span>
                  </span>
                </label>
                <span className={`shrink-0 font-display text-lg font-bold ${sc && sc !== "error" && sc.xpts_gain < 0 ? "text-bad" : "text-good"}`}>
                  {!sc ? "…" : sc === "error" ? "—" : signed(sc.xpts_gain)}
                </span>
              </div>
              {sc && sc !== "error" && sc.problems.length > 0 && (
                <div className="text-[11.5px] text-bad">Some moves no longer work (e.g. a price changed): {sc.problems[0].message}</div>
              )}
              <div className="flex gap-3 text-[13px] font-semibold">
                <Link href={openHref(d)} className="no-underline">Open</Link>
                <button type="button" onClick={() => { setRenaming(d); setNewName(d.name); }} className="text-link">Rename</button>
                {confirmDelete === d.id ? (
                  <span className="flex gap-2 text-text2">
                    Delete?
                    <button type="button" className="text-bad" onClick={() => { deleteDraft(d.id); track("draft_deleted"); setSelected((s) => s.filter((x) => x !== d.id)); setConfirmDelete(null); reload(); }}>
                      Yes
                    </button>
                    <button type="button" onClick={() => setConfirmDelete(null)}>No</button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirmDelete(d.id)} className="text-text3">Delete</button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {compared.length >= 2 && <Comparison drafts={compared} scores={scores} />}

      {renaming && (
        <Sheet title="Rename draft" onClose={() => setRenaming(null)}>
          <input value={newName} maxLength={60} onChange={(e) => setNewName(e.target.value)} aria-label="New name" className="h-10 rounded-lg border border-input-line bg-input px-3 text-sm text-text" />
          <button
            type="button"
            onClick={() => { renameDraft(renaming.id, newName); setRenaming(null); reload(); }}
            className="h-11 rounded-xl bg-accent text-sm font-semibold text-white"
          >
            Save name
          </button>
        </Sheet>
      )}
    </main>
  );
}

function Comparison({ drafts, scores }: { drafts: Draft[]; scores: Record<string, WhatIfResponse | "error"> }) {
  useEffect(() => {
    track("drafts_compared", { count: drafts.length });
  }, [drafts.length]);
  const ready = drafts.map((d) => scores[d.id]).every((s) => s && s !== "error");
  if (!ready) return <div className="text-xs text-text3">Scoring drafts…</div>;
  const rs = drafts.map((d) => scores[d.id] as WhatIfResponse);
  const gws = rs[0].gws;
  const best = (vals: number[]) => Math.max(...vals);
  const row = (label: string, vals: string[], highlight?: number[]) => (
    <tr className="border-t border-line">
      <td className="py-1.5 pr-2 text-text3">{label}</td>
      {vals.map((v, i) => (
        <td key={i} className={`py-1.5 text-right font-semibold ${highlight && highlight[i] === best(highlight) ? "text-good" : ""}`}>{v}</td>
      ))}
    </tr>
  );
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-cap-line bg-cap-bg p-3.5" data-testid="draft-compare">
      <div className="font-display text-base font-bold">Comparison</div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th />
              {drafts.map((d) => (
                <th key={d.id} className="pb-1 pl-3 text-right align-bottom text-xs font-semibold">
                  <span className="ml-auto block max-w-[110px] truncate">{d.name}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {row("Total vs no transfers", rs.map((r) => signed(r.xpts_gain)), rs.map((r) => r.xpts_gain))}
            {gws.map((g, k) => row(`GW${g}`, rs.map((r) => pts(r.weeks[k]?.xpts ?? 0)), rs.map((r) => r.weeks[k]?.xpts ?? 0)))}
            {row("Transfers", rs.map((r) => String(r.weeks.reduce((s, w) => s + w.moves.length, 0))))}
            {row("Hits", rs.map((r) => { const h = r.weeks.reduce((s, w) => s + w.hits, 0); return h ? `−${4 * h}` : "0"; }))}
            {row("Chips", rs.map((r) => r.weeks.filter((w) => w.chip).map((w) => `${CHIP_LABELS[w.chip!]} GW${w.gw}`).join(", ") || "—"))}
            {row(`Bank after GW${gws[gws.length - 1]}`, rs.map((r) => money(r.weeks[r.weeks.length - 1]?.bank ?? 0)))}
            {row(`Free transfers for GW${gws[gws.length - 1] + 1}`, rs.map((r) => String(r.free_transfers_after)))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
