"use client";

import { useEffect, useState } from "react";
import { track } from "@/lib/analytics";
import { ApiError, askPlans, type PlanParams } from "@/lib/api";
import { signed } from "@/lib/format";
import type { Plan, PlansResponse } from "@/lib/types";

// Questions about a plan. Every answer comes from re-running the optimizer with one thing
// changed (a hit allowed, a player kept, a player ruled out) and comparing the numbers. No AI
// writes these: the sentences are filled in from the solver's results.

type Question =
  | { kind: "hit"; label: string }
  | { kind: "why"; label: string; player: number }
  | { kind: "keep"; label: string; player: number }
  | { kind: "none"; label: string };

interface Answer {
  text: string;
  action?: { label: string; run: () => void };
}

const movesOf = (plan: Plan, data: PlansResponse) => {
  const first = plan.gameweeks[0];
  const name = (id: number) => data.players[id]?.name ?? "?";
  return first.moves.length ? first.moves.map((m) => `${name(m.player_out)} → ${name(m.player_in)}`).join(", ") : "no transfers this week";
};

/** "2.1 more than", "0.8 fewer than", "about the same as" (this plan). */
function versus(alt: number, base: number): string {
  const d = alt - base;
  if (Math.abs(d) < 0.05) return "about the same as";
  return `${Math.abs(d).toFixed(1)} ${d > 0 ? "more than" : "fewer than"}`;
}

export function AskPlan({ plan, data, params, onAllowHits }: { plan: Plan; data: PlansResponse; params: PlanParams; onAllowHits: (hits: number) => void }) {
  const [asked, setAsked] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setAsked(null);
    setAnswer(null);
  }, [plan.rank, data]);

  const first = plan.gameweeks[0];
  const name = (id: number) => data.players[id]?.name ?? "?";
  const h = `${data.horizon} GW${data.horizon === 1 ? "" : "s"}`;
  // In a Wildcard or Free Hit week everything changes at once, so these questions don't apply.
  if (first.chip === "wildcard" || first.chip === "freehit") return null;

  const questions: Question[] = [
    ...first.moves.slice(0, 2).map((m): Question => ({ kind: "why", label: `Why ${name(m.player_in)}?`, player: m.player_in })),
    ...first.moves.slice(0, 2).map((m): Question => ({ kind: "keep", label: `What if I keep ${name(m.player_out)}?`, player: m.player_out })),
    ...(params.hits < 3 ? [{ kind: "hit", label: "What if I take a hit?" } as Question] : []),
    ...(plan.is_roll ? [] : [{ kind: "none", label: "What if I make no transfers?" } as Question]),
  ];

  async function ask(q: Question) {
    setAsked(q.label);
    setAnswer(null);
    track("plan_question", { kind: q.kind, rank: plan.rank });
    if (q.kind === "none") {
      const chips = plan.chip_xpts > 0.05 ? ` ${signed(plan.chip_xpts)} of that comes from the chip, which you could still play without the transfers.` : "";
      setAnswer({ text: `Over ${h}, this plan is projected ${signed(plan.xpts_gain)} points against making no transfers.${chips} Making none would bank your free transfer for later.` });
      return;
    }
    setBusy(true);
    try {
      if (q.kind === "hit") {
        const hits = params.hits + 1;
        const alt = (await askPlans({ ...params, hits })).plans[0];
        if (!alt || alt.hits <= plan.hits) {
          setAnswer({ text: `Even with a hit allowed, the planner doesn't take one: no extra transfer is projected to earn back its 4 points over ${h}.` });
        } else {
          const res = await askPlans({ ...params, hits });
          setAnswer({
            text: `With a hit allowed, the best plan is ${movesOf(alt, res)} for −${4 * alt.hits}. After the hit it's projected ${signed(alt.xpts_gain)}, ${versus(alt.xpts_gain, plan.xpts_gain)} this plan. Careful: when we replayed real seasons, hits lost points on average.`,
            action: { label: "Show plans with a hit allowed", run: () => onAllowHits(hits) },
          });
        }
        return;
      }
      const res = await askPlans(params, q.kind === "why" ? { ban: [q.player] } : { keep: [q.player] });
      const alt = res.plans[0];
      const who = name(q.player);
      if (!alt) {
        setAnswer({ text: q.kind === "why" ? `Without ${who}, the planner finds no move worth making.` : `Keeping ${who}, the planner finds no move worth making.` });
      } else if (q.kind === "why") {
        const d = plan.xpts_gain - alt.xpts_gain;
        setAnswer({
          text:
            `Without ${who}, the best plan is ${movesOf(alt, res)}: ${signed(alt.xpts_gain)} over ${h}, ${versus(alt.xpts_gain, plan.xpts_gain)} this plan.` +
            (d > 0.05 ? ` So ${who} is worth about ${d.toFixed(1)} points more than the next best option.` : ` So it's a close call between them.`),
        });
      } else {
        setAnswer({ text: `Keeping ${who}, the best plan is ${movesOf(alt, res)}: ${signed(alt.xpts_gain)} over ${h}, ${versus(alt.xpts_gain, plan.xpts_gain)} this plan.` });
      }
    } catch (e) {
      setAnswer({ text: e instanceof ApiError ? e.message : "Couldn't work that out. Try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2" data-testid="ask-plan">
      <div className="text-xs font-semibold text-text3">ASK ABOUT THIS PLAN</div>
      <div className="flex flex-wrap gap-1.5">
        {questions.map((q) => (
          <button
            key={q.label}
            type="button"
            disabled={busy}
            aria-pressed={asked === q.label}
            onClick={() => ask(q)}
            className={`rounded-full px-2.5 py-1.5 text-left text-xs font-semibold disabled:opacity-60 ${asked === q.label ? "bg-accent text-white" : "bg-pill text-link"}`}
          >
            {q.label}
          </button>
        ))}
      </div>
      {asked && (
        <div className="flex flex-col gap-1.5 rounded-[10px] bg-surface2 px-3 py-2.5 text-[13px] leading-[1.45]" role="status" data-testid="ask-answer">
          {answer ? answer.text : "Re-running the planner…"}
          {answer?.action && (
            <button type="button" onClick={answer.action.run} className="self-start text-[13px] font-semibold text-link">
              {answer.action.label} →
            </button>
          )}
          {answer && <div className="text-[11.5px] text-text3">Worked out by the planner, not written by AI.</div>}
        </div>
      )}
    </div>
  );
}
