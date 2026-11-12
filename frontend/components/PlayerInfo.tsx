"use client";

import Link from "next/link";
import { useState } from "react";
import { FixtureStrip } from "@/components/FixtureStrip";
import { PriceMove } from "@/components/PriceMove";
import { Sheet } from "@/components/Sheet";
import { track } from "@/lib/analytics";
import { money, pts } from "@/lib/format";
import type { Player } from "@/lib/types";

/** A player's name you can tap for his details. Looks like the text around it. */
export function PlayerTap({ player, onOpen, className = "", children }: { player: Player | undefined; onOpen: (p: Player) => void; className?: string; children?: React.ReactNode }) {
  if (!player) return <span className={className}>{children ?? "?"}</span>;
  return (
    <button type="button" onClick={() => onOpen(player)} aria-label={`${player.name}: details`} className={`inline text-left ${className}`} data-testid="player-tap">
      {children ?? player.name}
    </button>
  );
}

/** Fixtures, projected points, price and ownership for one player, as a bottom sheet. */
function PlayerInfoSheet({ player, nRivals, compareHref, onClose }: { player: Player; nRivals: number; compareHref: string | null; onClose: () => void }) {
  return (
    <Sheet title={player.name} onClose={onClose}>
      <div className="text-[13px] text-text2">
        {player.club} · {player.position} · {money(player.price)}
        <PriceMove change={player.price_change} />
        {nRivals ? ` · ${player.rivals_owned}/${nRivals} rivals own him` : ""}
      </div>
      {player.news && <div className="rounded-lg bg-warn-bg px-3 py-2 text-[12.5px] text-warn-text">{player.news}</div>}
      <FixtureStrip gws={player.gws} />
      <div className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1 text-[13px]">
        {player.gws.map((g) => (
          <div key={g.gw} className="contents">
            <span className="text-text3">GW{g.gw}</span>
            <span className="truncate">{g.fixture}</span>
            <span className="text-right font-semibold">{pts(g.xpts)}</span>
          </div>
        ))}
      </div>
      <div className="text-[11.5px] text-text3">Numbers on the right are expected points (xPts).</div>
      {compareHref && (
        <Link href={compareHref} onClick={() => track("compare_opened", { from: "info" })} className="self-start text-[13px] font-semibold no-underline">
          Compare with another player →
        </Link>
      )}
    </Sheet>
  );
}

/** `open(player)` shows the sheet; render `sheet` once anywhere on the page. */
export function usePlayerInfo(nRivals: number, compareBase: string | null) {
  const [player, setPlayer] = useState<Player | null>(null);
  const open = (p: Player) => {
    setPlayer(p);
    track("player_details_opened", { mode: "info", level: null });
  };
  const sheet = player ? (
    <PlayerInfoSheet player={player} nRivals={nRivals} compareHref={compareBase ? `${compareBase}${player.id}` : null} onClose={() => setPlayer(null)} />
  ) : null;
  return { open, sheet };
}
