"use client";

import { useState } from "react";
import { track } from "@/lib/analytics";

/** A link that opens the app with this league already found, so a friend only taps their name. */
export const inviteUrl = (origin: string, leagueId: number) => `${origin}/?league=${leagueId}`;

export function InviteLeague({ leagueId, leagueName, className = "" }: { leagueId: number; leagueName: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const invite = async () => {
    const url = inviteUrl(window.location.origin, leagueId);
    const text = `Plan your FPL transfers against our league (${leagueName}). Open this and tap your name:`;
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ text, url });
        track("league_invite_shared", { method: "share" });
      } catch {
        /* closed the share sheet */
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(`${text} ${url}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      track("league_invite_shared", { method: "copy" });
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <button type="button" onClick={invite} data-testid="invite-league" className={`text-[13px] font-semibold text-link ${className}`}>
      {copied ? "Invite link copied ✓" : "Invite your league"}
    </button>
  );
}
