"use client";

import { useEffect, useState } from "react";
import { getExplanation, planQuery, type PlanParams } from "@/lib/api";
import { track } from "@/lib/analytics";
import type { ExplainResponse } from "@/lib/types";

/** The Claude-written reason for a plan; null while loading. */
export function useExplanation(params: PlanParams, rank: number): ExplainResponse | null {
  const key = `${planQuery(params)}&rank=${rank}`;
  const [result, setResult] = useState<{ key: string; value: ExplainResponse } | null>(null);
  useEffect(() => {
    let live = true;
    getExplanation(params, rank).then((value) => {
      if (!live) return;
      setResult({ key, value });
      track(value.status === "ok" ? "reason_shown" : "reason_missing", { rank, status: value.status });
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return result && result.key === key ? result.value : null;
}

/** "Why this plan" and "Watch out", or nothing if there's no reason (no key, error, failed check). */
export function Why({ explanation, label = "Why this plan" }: { explanation: Pick<ExplainResponse, "status" | "why" | "watch_out"> | null; label?: string }) {
  if (explanation && explanation.status !== "ok") return null;
  return (
    <>
      <div className="flex flex-col gap-1 rounded-[10px] bg-why-bg px-3 py-2.5" aria-live="polite">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-why-label">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M7 1l1.6 3.9L12.5 6.5 8.6 8.1 7 12 5.4 8.1 1.5 6.5l3.9-1.6z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          </svg>
          {label}
        </div>
        {explanation ? (
          <div className="text-[13px] leading-[1.45]" data-testid="why">{explanation.why}</div>
        ) : (
          <div className="flex flex-col gap-1.5 py-0.5" role="status" aria-label="Writing the reason">
            <div className="h-2.5 w-full animate-pulse rounded bg-why-label/20" />
            <div className="h-2.5 w-2/3 animate-pulse rounded bg-why-label/20" />
          </div>
        )}
      </div>
      {explanation?.watch_out && (
        <div className="flex items-start gap-2 rounded-[10px] bg-warn-bg px-2.5 py-2 text-[12.5px] leading-[1.4] text-warn-text">
          <span className="shrink-0 font-bold">Watch out:</span>
          <span>{explanation.watch_out}</span>
        </div>
      )}
    </>
  );
}
