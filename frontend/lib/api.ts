import type { ChipAdvice, ExplainResponse, PlansResponse, ResolveResponse, RivalsProgress, Strategy, TeamResponse } from "./types";

export class ApiError extends Error {}

async function getJSON<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("Couldn't reach the planner. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail = "Something went wrong. Try again in a moment.";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail);
  }
  return res.json() as Promise<T>;
}

export const resolveInput = (input: string) =>
  getJSON<ResolveResponse>(`/api/resolve?input=${encodeURIComponent(input)}`);

export const getTeam = (entry: number, league: number | null) =>
  getJSON<TeamResponse>(`/api/team/${entry}${league !== null ? `?league=${league}` : ""}`);

export const getRivals = (entry: number, league: number | null) =>
  getJSON<RivalsProgress>(`/api/rivals?team=${entry}${league !== null ? `&league=${league}` : ""}`);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Polls until the rivals' squads are loaded (the backend fetches them politely, ~1 a second). */
export async function waitForRivals(
  entry: number,
  league: number | null,
  onProgress: (p: RivalsProgress) => void,
  isLive: () => boolean = () => true,
): Promise<void> {
  for (;;) {
    const progress = await getRivals(entry, league);
    if (!isLive()) return;
    onProgress(progress);
    if (progress.ready) return;
    await sleep(1000);
  }
}

export interface PlanParams {
  team: number;
  league: number | null;
  strategy: Strategy;
  horizon: number;
  hits: number;
  wildcard: number | null; // the GW you chose to play it in
  freehit: number | null;
  chips: boolean; // let the planner play Bench Boost / Triple Captain
}

const gwParam = (v: string | null) => (v && Number(v) > 0 ? Number(v) : null);

export function readPlanParams(search: URLSearchParams): PlanParams {
  const league = search.get("league");
  const strategy = search.get("strategy");
  return {
    team: Number(search.get("team")),
    league: league === null ? null : Number(league),
    strategy: strategy === "protect" || strategy === "risky" ? strategy : "balanced",
    horizon: Math.min(5, Math.max(1, Number(search.get("horizon") ?? 4) || 4)),
    hits: Math.min(4, Math.max(0, Number(search.get("hits") ?? 0) || 0)),
    wildcard: gwParam(search.get("wildcard")),
    freehit: gwParam(search.get("freehit")),
    chips: search.get("chips") !== "0",
  };
}

/** Query for the backend API. */
export function planQuery(p: PlanParams): string {
  const q = new URLSearchParams({ team: String(p.team), strategy: p.strategy, horizon: String(p.horizon), max_hits: String(p.hits) });
  if (p.league !== null) q.set("league", String(p.league));
  if (p.wildcard !== null) q.set("wildcard", String(p.wildcard));
  if (p.freehit !== null) q.set("freehit", String(p.freehit));
  if (!p.chips) q.set("chips", "false");
  return q.toString();
}

/** Query for the plans page URL (shareable). */
export function pageQuery(p: PlanParams): string {
  const q = new URLSearchParams({ team: String(p.team), strategy: p.strategy, horizon: String(p.horizon), hits: String(p.hits) });
  if (p.league !== null) q.set("league", String(p.league));
  if (p.wildcard !== null) q.set("wildcard", String(p.wildcard));
  if (p.freehit !== null) q.set("freehit", String(p.freehit));
  if (!p.chips) q.set("chips", "0");
  return q.toString();
}

const adviceCache = new Map<string, Promise<ChipAdvice[]>>();

/** What a Wildcard / Free Hit this week would add (computed lazily: it builds extra plan sets). */
export function getChipAdvice(p: PlanParams): Promise<ChipAdvice[]> {
  const key = planQuery({ ...p, wildcard: null, freehit: null });
  let pending = adviceCache.get(key);
  if (!pending) {
    pending = getJSON<ChipAdvice[]>(`/api/chip-advice?${key}`).catch(() => {
      adviceCache.delete(key);
      return [];
    });
    adviceCache.set(key, pending);
  }
  return pending;
}

// Plan sets are cached for the session so the detail screen, going back, and switching
// strategy (prefetched in the background) are instant.
const planCache = new Map<string, Promise<PlansResponse>>();

export function getPlans(p: PlanParams): Promise<PlansResponse> {
  const key = planQuery(p);
  let pending = planCache.get(key);
  if (!pending) {
    pending = getJSON<PlansResponse>(`/api/plans?${key}`);
    pending.catch(() => planCache.delete(key));
    planCache.set(key, pending);
  }
  return pending;
}

// Claude-written reasons, one request per plan so each card fills in as soon as it's ready.
// Failures resolve to "unavailable": a missing reason never breaks the page.
const explainCache = new Map<string, Promise<ExplainResponse>>();

export function getExplanation(p: PlanParams, rank: number): Promise<ExplainResponse> {
  const key = `${planQuery(p)}&rank=${rank}`;
  let pending = explainCache.get(key);
  if (!pending) {
    pending = getJSON<ExplainResponse>(`/api/explain?${key}`).catch(() => {
      explainCache.delete(key);
      return { rank, status: "unavailable" as const, why: null, watch_out: null };
    });
    explainCache.set(key, pending);
  }
  return pending;
}
