import { reportError, scrubUrl, track } from "./analytics";
import type { AnalysisResponse, ChipName, PlayersResponse, WhatIfMove, WhatIfRequest, WhatIfResponse, WhatIfSwap, ExplainResponse, PlansResponse, WeekResponse, ResolveResponse, RivalsProgress, Strategy, TeamResponse } from "./types";

export class ApiError extends Error {}

/** Failed requests worth knowing about: server errors, rate limits, and requests we built wrong. */
function reportFailure(path: string, status: number | null, detail: string): void {
  const endpoint = scrubUrl(path);
  if (status === null) reportError("network", "couldn't reach the server", { endpoint });
  else if (status >= 500 || status === 429 || status === 422) reportError("api", detail, { endpoint, status });
}

async function getJSON<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    reportFailure(path, null, "");
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
    reportFailure(path, res.status, detail);
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

/** Plans with one thing changed, for questions about a plan: a player kept or ruled out. */
export function askPlans(p: PlanParams, extra: { keep?: number[]; ban?: number[] } = {}): Promise<PlansResponse> {
  let key = planQuery(p);
  if (extra.keep?.length) key += `&keep=${extra.keep.join(",")}`;
  if (extra.ban?.length) key += `&ban=${extra.ban.join(",")}`;
  let pending = planCache.get(key);
  if (!pending) {
    pending = getJSON<PlansResponse>(`/api/plans?${key}`);
    pending.catch(() => planCache.delete(key));
    planCache.set(key, pending);
  }
  return pending;
}

export const getWeek = (team: number, league: number | null) =>
  getJSON<WeekResponse>(`/api/week?team=${team}${league !== null ? `&league=${league}` : ""}`);

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

export interface FeedbackContext {
  page: string;
  strategy?: string;
  horizon?: number;
  rank?: number;
  gw?: number;
}

/** Anonymous feedback: logged by the backend and, if tracking is on, sent to PostHog. */
export async function sendFeedback(body: { kind: "plan" | "general"; useful: boolean | null; text: string; context: FeedbackContext }): Promise<void> {
  // The note goes to PostHog too, where it's kept (Render's logs expire). It's text the user chose
  // to write; no team ID is attached.
  track("feedback_sent", {
    kind: body.kind, useful: body.useful, text: body.text.trim().slice(0, 1000) || null, page: body.context.page,
    strategy: body.context.strategy ?? null, rank: body.context.rank ?? null,
  });
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError("Couldn't send feedback.");
}

// ---- phase 8 ----
const analysisCache = new Map<string, Promise<AnalysisResponse>>();

export function getAnalysis(team: number, league: number | null, strategy: Strategy, horizon = 4): Promise<AnalysisResponse> {
  const q = new URLSearchParams({ team: String(team), strategy, horizon: String(horizon) });
  if (league !== null) q.set("league", String(league));
  const key = q.toString();
  let pending = analysisCache.get(key);
  if (!pending) {
    pending = getJSON<AnalysisResponse>(`/api/analysis?${key}`);
    pending.catch(() => analysisCache.delete(key));
    analysisCache.set(key, pending);
  }
  return pending;
}

const playersCache = new Map<string, Promise<PlayersResponse>>();

/** Every player with projections (for the what-if search); fetched once per session. */
export function getAllPlayers(team: number, league: number | null): Promise<PlayersResponse> {
  const key = `${team}:${league}`;
  let pending = playersCache.get(key);
  if (!pending) {
    pending = getJSON<PlayersResponse>(`/api/players?team=${team}${league !== null ? `&league=${league}` : ""}`);
    pending.catch(() => playersCache.delete(key));
    playersCache.set(key, pending);
  }
  return pending;
}

export async function postWhatIf(body: WhatIfRequest): Promise<WhatIfResponse> {
  let res: Response;
  try {
    res = await fetch("/api/what-if", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    reportFailure("/api/what-if", null, "");
    throw new ApiError("Couldn't reach the planner. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail = "Couldn't score that plan. Try again.";
    try {
      const b = await res.json();
      if (typeof b?.detail === "string") detail = b.detail;
    } catch {
      /* not JSON */
    }
    reportFailure("/api/what-if", res.status, detail);
    throw new ApiError(detail);
  }
  return res.json() as Promise<WhatIfResponse>;
}

/** What-if moves, captains and chips in the page address, so a what-if can be bookmarked or shared. */
export function encodeWhatIf(moves: WhatIfMove[], captains: Record<number, number>, chips: Record<number, string>, swaps: WhatIfSwap[] = []): string {
  const q = new URLSearchParams();
  if (moves.length) q.set("m", moves.map((m) => `${m.gw}.${m.out}.${m.into}`).join(","));
  if (swaps.length) q.set("s", swaps.map((s) => `${s.gw}.${s.bench}.${s.start}`).join(","));
  const caps = Object.entries(captains);
  if (caps.length) q.set("c", caps.map(([g, p]) => `${g}.${p}`).join(","));
  const ch = Object.entries(chips);
  if (ch.length) q.set("x", ch.map(([g, c]) => `${g}.${c}`).join(","));
  return q.toString();
}

export function decodeWhatIf(search: URLSearchParams): { moves: WhatIfMove[]; captains: Record<number, number>; chips: Record<number, ChipName>; swaps: WhatIfSwap[] } {
  const nums = (s: string) => s.split(".").map(Number);
  const moves = (search.get("m") ?? "").split(",").filter(Boolean).map(nums)
    .filter((a) => a.length === 3 && a.every((n) => Number.isInteger(n) && n > 0)).map(([gw, out, into]) => ({ gw, out, into }));
  const captains: Record<number, number> = {};
  for (const part of (search.get("c") ?? "").split(",").filter(Boolean)) {
    const [g, p] = nums(part);
    if (g > 0 && p > 0) captains[g] = p;
  }
  const chips: Record<number, ChipName> = {};
  for (const part of (search.get("x") ?? "").split(",").filter(Boolean)) {
    const [g, c] = part.split(".");
    if (Number(g) > 0 && ["wildcard", "freehit", "bboost", "3xc"].includes(c)) chips[Number(g)] = c as ChipName;
  }
  const swaps = (search.get("s") ?? "").split(",").filter(Boolean).map(nums)
    .filter((a) => a.length === 3 && a.every((n) => Number.isInteger(n) && n > 0)).map(([gw, bench, start]) => ({ gw, bench, start }));
  return { moves, captains, chips, swaps };
}

export interface ReplacementReason { player: number; status: "ok" | "unavailable" | "off"; why: string | null; watch_out: string | null }
const reasonCache = new Map<string, Promise<ReplacementReason>>();

/** Claude's reason for the top replacement of one squad player (cached for the session). */
export function getReplacementReason(team: number, league: number | null, strategy: Strategy, player: number): Promise<ReplacementReason> {
  const q = new URLSearchParams({ team: String(team), strategy, player: String(player), horizon: "4" });
  if (league !== null) q.set("league", String(league));
  const key = q.toString();
  let pending = reasonCache.get(key);
  if (!pending) {
    pending = getJSON<ReplacementReason>(`/api/analysis/explain?${key}`).catch(() => {
      reasonCache.delete(key);
      return { player, status: "unavailable" as const, why: null, watch_out: null };
    });
    reasonCache.set(key, pending);
  }
  return pending;
}
