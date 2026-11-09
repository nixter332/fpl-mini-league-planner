"use client";

import { useEffect, useState } from "react";
import { track } from "@/lib/analytics";

const KEY = "tips:v1";

/** A one-time card for new visitors; "Got it" hides it for good (on this browser). */
export function Tips() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      setShow(localStorage.getItem(KEY) !== "seen");
    } catch {
      setShow(false);
    }
  }, []);
  if (!show) return null;
  const close = () => {
    setShow(false);
    track("tips_dismissed");
    try {
      localStorage.setItem(KEY, "seen");
    } catch {
      /* private mode */
    }
  };
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-accent-line bg-surface p-3.5" data-testid="tips">
      <div className="font-display text-[15px] font-bold">New here? Three things</div>
      <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-[13px] leading-[1.45] text-text2">
        <li>
          <b className="text-text">xPts</b> are the points our model expects a player to score. The number under each shirt is
          for the gameweek you pick above the pitch.
        </li>
        <li>
          <b className="text-text">Tap any player</b> for his next fixtures (green easy, red hard). <b className="text-text">Weak spots</b>{" "}
          colours the shirts worth replacing and lists the best swaps.
        </li>
        <li>
          <b className="text-text">See transfer plans</b> gives the best moves against your league. Protect lead plays it safe;
          Risky backs players your rivals don&apos;t have.
        </li>
      </ul>
      <button type="button" onClick={close} className="self-end rounded-lg bg-pill px-3 py-1.5 text-xs font-semibold text-link">
        Got it
      </button>
    </div>
  );
}
