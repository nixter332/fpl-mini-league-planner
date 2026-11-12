// What the bottom tab bar needs to link between screens (team, league, strategy), and whether the
// visitor is looking at the sample team. Kept for this browser tab only (sessionStorage).

import type { Strategy } from "./types";

export interface NavContext {
  team: number;
  league: number | null;
  strategy: Strategy;
}

const KEY = "nav:v1";
const DEMO_KEY = "demo:v1";

// The sample team behind "Try a sample team". Set NEXT_PUBLIC_DEMO_TEAM / _LEAGUE to change it.
export const DEMO_TEAM = Number(process.env.NEXT_PUBLIC_DEMO_TEAM ?? 5179483);
export const DEMO_LEAGUE = Number(process.env.NEXT_PUBLIC_DEMO_LEAGUE ?? 1883627);

export function rememberNav(ctx: NavContext): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(ctx));
  } catch {
    /* storage blocked: the tabs fall back to what the address shows */
  }
}

/** The remembered context, if it's for this team. */
export function loadNav(team: number): NavContext | null {
  try {
    const ctx = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
    return ctx?.team === team ? ctx : null;
  } catch {
    return null;
  }
}

export function startDemo(): void {
  try {
    sessionStorage.setItem(DEMO_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function endDemo(): void {
  try {
    sessionStorage.removeItem(DEMO_KEY);
  } catch {
    /* ignore */
  }
}

/** True while someone who tapped "Try a sample team" is looking at that team. */
export function isDemo(team: number): boolean {
  try {
    return team === DEMO_TEAM && sessionStorage.getItem(DEMO_KEY) === "1";
  } catch {
    return false;
  }
}
