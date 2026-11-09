"use client";

import { useState } from "react";
import { track } from "@/lib/analytics";
import { CHIP_LABELS, signed, strategyLabel } from "@/lib/format";
import type { Plan, PlansResponse } from "@/lib/types";

/** The plan as a short message for WhatsApp etc. Links to the start page, never to the user's team. */
export function shareText(plan: Plan, data: PlansResponse): string {
  const name = (id: number) => data.players[id]?.name ?? "?";
  const first = plan.gameweeks[0];
  const moves = first.moves.length ? first.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ") : "Roll the transfer";
  const chips = plan.gameweeks.filter((g) => g.chip).map((g) => `${CHIP_LABELS[g.chip!]} in GW${g.gw}`);
  return [
    `My GW${first.gw} plan (${strategyLabel(data.strategy)}): ${moves}.`,
    `Captain ${name(first.captain)}.`,
    chips.length ? `${chips.join(", ")}.` : "",
    `${signed(plan.xpts_gain)} expected points over ${data.horizon} GW${data.horizon === 1 ? "" : "s"}.`,
  ].filter(Boolean).join(" ");
}

export function SharePlan({ plan, data, className = "" }: { plan: Plan; data: PlansResponse; className?: string }) {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const text = shareText(plan, data);
    const url = window.location.origin;
    const intro = "Plan yours against your own mini-league:";
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ text: `${text}\n\n${intro}`, url });
        track("plan_shared", { method: "share", rank: plan.rank });
      } catch {
        /* closed the share sheet */
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(`${text}\n\n${intro} ${url}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      track("plan_shared", { method: "copy", rank: plan.rank });
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <button type="button" onClick={share} data-testid="share-plan" className={`text-sm font-semibold text-link ${className}`}>
      {copied ? "Copied ✓" : "Share"}
    </button>
  );
}
