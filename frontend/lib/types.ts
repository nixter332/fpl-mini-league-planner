// Mirrors backend/app/api/schemas.py. Prices are ints in tenths of a million.

export type Strategy = "protect" | "balanced" | "risky";
export type Position = "GKP" | "DEF" | "MID" | "FWD";

export interface Kit { body: string; sleeve: string; trim: string }
export interface Club { id: number; short_name: string; name: string; kit: Kit }

export interface Member { entry: number; player_name: string; entry_name: string; rank: number; total: number }
export interface ResolveResponse {
  type: "team" | "league";
  id: number;
  league_name: string | null;
  members: Member[];
  more_members: boolean;
}

export interface Gameweek { id: number; name: string; deadline: string }
export interface PlayerGw { gw: number; fixture: string; xpts: number }
export interface Player {
  id: number;
  name: string;
  position: Position;
  club: string;
  price: number;
  sell_price: number | null;
  status: string;
  news: string;
  doubtful: boolean;
  rivals_owned: number;
  rivals_captained: number;
  gws: PlayerGw[];
}

export interface LineupGw {
  gw: number;
  starting: number[];
  bench: number[];
  captain: number;
  vice: number;
  xpts: number;
  rivals_avg: number | null;
  edge: number | null;
}

export interface LeagueInfo { id: number; name: string; size: number | null }
export interface Standing {
  league: LeagueInfo;
  rank: number | null;
  total: number | null;
  leader_name: string | null;
  leader_entry_name: string | null;
  gap_to_first: number | null;
  n_rivals: number;
}

export interface RivalsProgress {
  league_id: number;
  loaded: number;
  total: number;
  ready: boolean;
}

export interface TeamResponse {
  entry: number;
  team_name: string;
  manager_name: string;
  picks_gw: number;
  free_transfers: number;
  bank: number;
  leagues: LeagueInfo[];
  standing: Standing | null;
  rivals: RivalsProgress | null; // null = no league; ready false = still loading in the background
  gameweeks: Gameweek[];
  lineups: LineupGw[];
  squad: number[];
  players: Record<string, Player>;
  clubs: Record<string, Club>;
  facts: string[];
}

export interface Move { player_out: number; player_in: number; out_price: number; in_price: number }
export interface PlanGw { gw: number; moves: Move[]; hits: number; free_transfers: number; bank: number; captain: number; vice: number }
export interface Threat { player: number; rivals_starting: number; xpts: number }
export interface HeadToHead {
  opponent_name: string;
  opponent_entry_name: string;
  opponent_rank: number;
  points_gap: number;
  you_xpts: number;
  them_xpts: number;
  shared_players: number;
  your_differentials: number[];
  their_differentials: number[];
  their_captain: number;
}
export interface Plan {
  rank: number;
  tag: "free" | "hit" | "roll";
  is_roll: boolean;
  proven_optimal: boolean;
  hits: number;
  xpts: number;
  xpts_gain: number;
  differential_gain: number;
  summary: string;
  gameweeks: PlanGw[];
  before: LineupGw;
  after: LineupGw;
  threats: Threat[];
  head_to_head: HeadToHead | null;
}
export interface PlansResponse {
  entry: number;
  strategy: Strategy;
  horizon: number;
  max_hits: number;
  gws: number[];
  free_transfers: number;
  bank: number;
  standing: Standing | null;
  captain_note: string;
  plans: Plan[];
  players: Record<string, Player>;
  clubs: Record<string, Club>;
  facts: string[];
  seconds: number;
}

export interface ExplainResponse {
  rank: number;
  status: "ok" | "unavailable" | "off";
  why: string | null;
  watch_out: string | null;
}
