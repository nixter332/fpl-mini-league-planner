// The last team opened on this device, so the start page can offer it again.
// Stored only in this browser (localStorage); nothing is sent to the server.

export interface RecentTeam {
  entry: number;
  league: number | null;
  name: string;
}

const KEY = "lastTeam";

export function saveRecentTeam(team: RecentTeam): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(team));
  } catch {
    /* private mode or storage blocked: just don't remember */
  }
}

export function loadRecentTeam(): RecentTeam | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const t = JSON.parse(raw);
    return typeof t?.entry === "number" && typeof t?.name === "string" ? t : null;
  } catch {
    return null;
  }
}

export function forgetRecentTeam(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
