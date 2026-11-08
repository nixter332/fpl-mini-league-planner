import type { Player, Strategy } from "./types";

export const money = (tenths: number) => `£${(tenths / 10).toFixed(1)}m`;
export const signed = (n: number) => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}`;
export const pts = (n: number) => n.toFixed(1);

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n.toLocaleString("en-GB") + (s[(v - 20) % 10] || s[v] || s[0]);
}

export function deadlineLabel(gwName: string, iso: string, index: number, now = new Date()): string {
  const deadline = new Date(iso);
  if (index === 0) {
    const when = deadline.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
    return `${gwName} deadline · ${when}`;
  }
  const days = Math.max(0, Math.round((deadline.getTime() - now.getTime()) / 86_400_000));
  return `${gwName.replace("Gameweek ", "GW")} · in ${days} day${days === 1 ? "" : "s"}`;
}

export function gwOf(player: Player, gw: number) {
  return player.gws.find((g) => g.gw === gw) ?? { gw, fixture: "—", xpts: 0 };
}

export const STRATEGIES: { key: Strategy; label: string; desc: string }[] = [
  {
    key: "protect",
    label: "Protect lead",
    desc: "The most expected points, whatever your rivals own. Best when you're ahead and just need to keep scoring.",
  },
  {
    key: "balanced",
    label: "Balanced",
    desc: "Most expected points, with a nudge toward players and captains your rivals don't have.",
  },
  {
    key: "risky",
    label: "Risky",
    desc: "Backs differentials and differential captains for a bigger swing. It can win you ground fast, or lose it. Best when you're behind.",
  },
];

export const strategyLabel = (s: Strategy) => STRATEGIES.find((x) => x.key === s)?.label ?? s;
