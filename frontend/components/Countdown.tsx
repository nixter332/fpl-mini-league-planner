"use client";

import { useEffect, useState } from "react";
import { timeLeft } from "@/lib/format";

/** "GW11 deadline · Sat 21 Nov, 16:30 · 3d 4h left", in the viewer's own time zone. Amber in the last day. */
export function Countdown({ gw, deadline }: { gw: number; deadline: string }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  if (now === null) return null;
  const at = new Date(deadline);
  const ms = at.getTime() - now;
  const when = at.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  const urgent = ms > 0 && ms < 86_400_000;
  return (
    <div
      data-testid="countdown"
      className={`flex items-center gap-2 rounded-xl px-3 py-2 text-[13px] ${urgent ? "bg-warn-bg text-warn-text" : "border border-line bg-surface text-text2"}`}
    >
      <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
        <circle cx="8" cy="9" r="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M8 6v3.2l2 1.3M6.5 1.5h3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      {ms > 0 ? (
        <>
          <span className="min-w-0 flex-1">
            <span className="font-semibold text-text">GW{gw} deadline</span> · {when}
          </span>
          <span className={`shrink-0 font-semibold ${urgent ? "" : "text-text"}`}>{timeLeft(ms)} left</span>
        </>
      ) : (
        <span>The GW{gw} deadline has passed. Plans move on to the next gameweek shortly.</span>
      )}
    </div>
  );
}
