import type { Club, Kit, Player, Position } from "@/lib/types";

export interface PitchPlayer {
  id: number;
  name: string;
  info: string; // e.g. the fixture; truncates first when space is tight
  value?: string; // e.g. xPts; always shown in full
  isCaptain?: boolean;
  isNew?: boolean;
  doubtful?: boolean;
  news?: string;
  kit: Kit;
}

const ROWS: Position[] = ["GKP", "DEF", "MID", "FWD"];

export function kitFor(player: Player, clubs: Record<string, Club>): Kit {
  if (player.position === "GKP") return clubs.GKP?.kit ?? { body: "#F5C518", sleeve: "#F5C518", trim: "#111111" };
  return clubs[player.club]?.kit ?? { body: "#94A0AF", sleeve: "#94A0AF", trim: "#FFFFFF" };
}

export function Shirt({ kit, highlight = false }: { kit: Kit; highlight?: boolean }) {
  const outline = highlight ? "#22C55E" : "rgba(0,0,0,0.35)";
  const w = highlight ? 2 : 0.8;
  return (
    <svg width="42" height="42" viewBox="0 0 40 40" aria-hidden="true">
      <path d="M12 4 L4 9 L7 17 L11 15.5 L11 8 Z" fill={kit.sleeve} stroke={outline} strokeWidth={w} strokeLinejoin="round" />
      <path d="M28 4 L36 9 L33 17 L29 15.5 L29 8 Z" fill={kit.sleeve} stroke={outline} strokeWidth={w} strokeLinejoin="round" />
      <path d="M12 4 C14 6.5 16.5 7.5 20 7.5 C23.5 7.5 26 6.5 28 4 L29 8 L29 36 L11 36 L11 8 Z" fill={kit.body} stroke={outline} strokeWidth={w} strokeLinejoin="round" />
      <path d="M15.5 5.2 C17 6.6 18.4 7 20 7 C21.6 7 23 6.6 24.5 5.2" fill="none" stroke={kit.trim} strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function PlayerToken({ p }: { p: PitchPlayer }) {
  return (
    <div className="flex min-w-0 max-w-[76px] flex-1 flex-col items-center gap-0.5" data-testid="pitch-player">
      <div className="relative h-[42px] w-[42px]">
        <Shirt kit={p.kit} highlight={p.isNew} />
        {p.isCaptain && (
          <div className="absolute -right-2 -top-[3px] flex h-[19px] w-[19px] items-center justify-center rounded-full border-[1.5px] border-white bg-[#0B0F14] text-[10.5px] font-bold text-white" aria-label="Captain">
            C
          </div>
        )}
        {p.isNew && (
          <div className="absolute -left-3 -top-1.5 flex h-[17px] items-center rounded-full bg-[#22C55E] px-[5px] text-[10px] font-bold text-[#052E16]">IN</div>
        )}
        {p.doubtful && !p.isNew && (
          <div
            className="absolute -left-2 -top-[3px] flex h-[19px] w-[19px] items-center justify-center rounded-full border-[1.5px] border-white bg-[#F59E0B] text-[11px] font-bold text-[#0B0F14]"
            title={p.news || "Doubtful"}
            aria-label={p.news ? `Doubtful: ${p.news}` : "Doubtful"}
          >
            !
          </div>
        )}
      </div>
      <div className="flex w-full flex-col overflow-hidden rounded-md shadow-[0_1px_2px_rgba(0,0,0,0.3)]">
        <div className="truncate bg-white px-[3px] py-0.5 text-center text-[11.5px] font-semibold text-[#0F172A]">{p.name}</div>
        <div className="flex justify-center gap-[3px] bg-[#0B0F14] px-[3px] py-0.5 text-[10.5px] text-white">
          <span className="min-w-0 truncate">{p.info}</span>
          {p.value && <span className="shrink-0">· {p.value}</span>}
        </div>
      </div>
    </div>
  );
}

export function Pitch({ players, positions }: { players: PitchPlayer[]; positions: Record<number, Position> }) {
  return (
    <div className="pitch relative h-[404px] shrink-0 overflow-hidden rounded-2xl">
      <div className="absolute inset-3 rounded border-[1.5px] border-white/40" />
      <div className="absolute left-3 right-3 top-1/2 border-t-[1.5px] border-white/40" />
      <div className="absolute left-1/2 top-1/2 -ml-9 -mt-9 h-[72px] w-[72px] rounded-full border-[1.5px] border-white/40" />
      <div className="absolute left-1/2 top-3 -ml-[75px] h-[52px] w-[150px] border-[1.5px] border-t-0 border-white/40" />
      <div className="relative flex h-full flex-col justify-around py-2">
        {ROWS.map((pos) => (
          <div key={pos} className="flex justify-evenly gap-1 px-2">
            {players.filter((p) => positions[p.id] === pos).map((p) => (
              <PlayerToken key={p.id} p={p} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function Bench({ players }: { players: PitchPlayer[] }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[14px] border border-line bg-surface px-1.5 py-2">
      <div className="pl-1.5 text-[11.5px] font-semibold text-text3">BENCH</div>
      <div className="flex justify-evenly">
        {players.map((p) => (
          <div key={p.id} className="flex w-[78px] flex-col items-center gap-0.5">
            <div className="max-w-[78px] truncate text-[11.5px] font-semibold">
              {p.doubtful ? "! " : ""}
              {p.name}
            </div>
            <div className="max-w-[78px] truncate text-[10.5px] text-text2">
              {p.info}
              {p.value ? ` · ${p.value}` : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
