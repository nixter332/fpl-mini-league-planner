"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { track } from "@/lib/analytics";
import { NO_CHOSEN_CHIPS, getChips, getPlans } from "@/lib/api";
import { pts, signed } from "@/lib/format";
import type { ChipsResponse, PlansResponse, Strategy } from "@/lib/types";

interface Props {
  team: number;
  league: number; // 0 = no league
  strategy: Strategy;
  gw: number;
  captain: { name: string; xpts: number } | null;
  rivalsReady: boolean; // plans need the rivals' squads first
  plansHref: string;
  chipsHref: string;
}

/** "Before the GW11 deadline": this week's transfer, captain and chip, each linking to its screen.
 * The transfer line reuses the default plan set the team page already prefetches. */
export function DeadlineChecklist({ team, league, strategy, gw, captain, rivalsReady, plansHref, chipsHref }: Props) {
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [chips, setChips] = useState<ChipsResponse | null>(null);
  const [plansFailed, setPlansFailed] = useState(false);
  const [chipsFailed, setChipsFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setChips(null);
    getChips(team, league).then((c) => live && setChips(c)).catch(() => live && setChipsFailed(true));
    return () => {
      live = false;
    };
  }, [team, league]);

  useEffect(() => {
    if (!rivalsReady) return;
    let live = true;
    setPlans(null);
    getPlans({ team, league, strategy, horizon: 4, hits: 0, ...NO_CHOSEN_CHIPS, chips: false })
      .then((p) => live && setPlans(p))
      .catch(() => live && setPlansFailed(true));
    return () => {
      live = false;
    };
  }, [team, league, strategy, rivalsReady]);

  const plan = plans?.plans[0];
  const moves = plan?.gameweeks[0]?.moves ?? [];
  const name = (pid: number) => plans?.players[pid]?.name ?? "?";
  const transfer = plansFailed
    ? "Open Plans to see this week's transfer."
    : !plan
      ? "Working out your best transfer…"
      : plan.is_roll || moves.length === 0
        ? "No transfer: save it for next week."
        : `${moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ")} (${signed(plan.xpts_gain)} over 4 GWs)`;

  const ranked = (chips?.chips ?? []).filter((c) => c.ranked && c.best_gw !== null);
  const now = ranked.find((c) => c.play_now);
  const chip = chipsFailed
    ? "Open Chips to see when to play them."
    : !chips
      ? "Checking your chips…"
      : now
        ? `Play your ${now.label} this week.`
        : ranked.length > 0
          ? `No chip this week. ${ranked.map((c) => `${c.label}: ${c.advised ? "best" : "best projected"} GW${c.best_gw}`).join(" · ")}`
          : chips.chips.length > 0
            ? "No chip this week."
            : "No chips to play before the next half.";

  const rows = [
    { key: "transfer", label: "Transfer", text: transfer, href: plansHref },
    { key: "captain", label: "Captain", text: captain ? `${captain.name} (${pts(captain.xpts)} expected points)` : "—", href: plansHref },
    { key: "chip", label: "Chip", text: chip, href: chipsHref },
  ];
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-3.5" data-testid="deadline-checklist">
      <h2 className="m-0 font-display text-[15px] font-bold">Before the GW{gw} deadline</h2>
      {rows.map((r) => (
        <Link
          key={r.key}
          href={r.href}
          onClick={() => track("checklist_opened", { row: r.key })}
          className="flex items-start justify-between gap-3 border-t border-line pt-2 text-text no-underline first:border-t-0 first:pt-0"
          data-testid={`checklist-${r.key}`}
        >
          <span className="flex min-w-0 flex-col">
            <span className="text-[11px] font-semibold text-text3">{r.label.toUpperCase()}</span>
            <span className="text-[13px] leading-[1.4]">{r.text}</span>
          </span>
          <span className="shrink-0 pt-3 text-text3" aria-hidden="true">›</span>
        </Link>
      ))}
    </section>
  );
}
