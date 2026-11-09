import type { PlayerGw } from "@/lib/types";

// FPL's difficulty colours: 1-2 easy (green), 3 neutral, 4-5 hard (red).
const COLOURS: Record<number, string> = {
  1: "bg-[#0F7B3D] text-white",
  2: "bg-[#22C55E] text-[#052E16]",
  3: "bg-[#CBD5E1] text-[#0F172A]",
  4: "bg-[#F87171] text-[#450A0A]",
  5: "bg-[#991B1B] text-white",
};

/** The next few fixtures as coloured boxes: opponent, home (upper case) or away (lower case). */
export function FixtureStrip({ gws, from, count = 5 }: { gws: PlayerGw[]; from?: number; count?: number }) {
  const weeks = gws.filter((g) => from === undefined || g.gw >= from).slice(0, count);
  return (
    <div className="flex gap-0.5" data-testid="fixture-strip" aria-label="Next fixtures">
      {weeks.map((g) => {
        const parts = g.fixture === "—" ? [] : g.fixture.split(", ");
        return (
          <div key={g.gw} className="flex min-w-0 flex-1 flex-col items-stretch gap-px" title={`GW${g.gw}: ${g.fixture}`}>
            <div className="text-center text-[9.5px] text-text3">GW{g.gw}</div>
            {parts.length === 0 ? (
              <div className="rounded-[3px] bg-seg py-0.5 text-center text-[10px] text-text3">–</div>
            ) : (
              <div className="flex gap-px">
                {parts.map((part, i) => {
                  const [opp, venue] = part.split(" ");
                  const d = g.difficulty?.[i] ?? 3; // older backends send no ratings: show neutral
                  return (
                    <div key={i} className={`min-w-0 flex-1 truncate rounded-[3px] py-0.5 text-center text-[10px] font-semibold ${COLOURS[d] ?? COLOURS[3]}`}>
                      {venue === "(H)" ? opp.toUpperCase() : opp.toLowerCase()}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
