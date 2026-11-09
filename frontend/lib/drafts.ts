// Drafts (phase 9): named what-if setups saved on this device (localStorage). Saving across
// devices comes with the phase 6 database. Every access is wrapped: if storage is blocked (private
// mode), drafts simply aren't kept, and nothing breaks.

import type { ChipName, Strategy, WhatIfMove, WhatIfSwap } from "./types";

export interface Draft {
  id: string;
  name: string;
  team: number;
  league: number | null;
  strategy: Strategy;
  moves: WhatIfMove[];
  captains: Record<number, number>;
  chips: Record<number, ChipName>;
  swaps?: WhatIfSwap[]; // lineup choices (older drafts have none)
  createdAt: number;
  updatedAt: number;
}

const KEY = "drafts:v1";
const MAX_DRAFTS = 50;

function readAll(): Draft[] {
  try {
    const raw = localStorage.getItem(KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.filter((d) => typeof d?.id === "string" && typeof d?.team === "number") : [];
  } catch {
    return [];
  }
}

function writeAll(drafts: Draft[]): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify(drafts.slice(0, MAX_DRAFTS)));
    return true;
  } catch {
    return false;
  }
}

/** This team's drafts, most recently changed first. */
export function listDrafts(team: number): Draft[] {
  return readAll().filter((d) => d.team === team).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getDraft(id: string): Draft | null {
  return readAll().find((d) => d.id === id) ?? null;
}

/** Create (no id) or update a draft. Returns it, or null if the device won't store it. */
export function saveDraft(draft: Omit<Draft, "id" | "createdAt" | "updatedAt"> & { id?: string }): Draft | null {
  const all = readAll();
  const now = Date.now();
  const existing = draft.id ? all.find((d) => d.id === draft.id) : undefined;
  const saved: Draft = {
    ...draft,
    name: draft.name.trim().slice(0, 60) || "Untitled draft",
    id: existing?.id ?? `d${now.toString(36)}${Math.random().toString(36).slice(2, 7)}`,
    createdAt: existing?.createdAt ?? now,
    updatedAt: now,
  };
  const rest = all.filter((d) => d.id !== saved.id);
  return writeAll([saved, ...rest]) ? saved : null;
}

export function renameDraft(id: string, name: string): void {
  const all = readAll();
  const d = all.find((x) => x.id === id);
  if (!d) return;
  d.name = name.trim().slice(0, 60) || d.name;
  d.updatedAt = Date.now();
  writeAll(all);
}

export function deleteDraft(id: string): void {
  writeAll(readAll().filter((d) => d.id !== id));
}

/** A sensible default name from what the draft does, e.g. "Wildcard GW12" or "3 transfers". */
export function suggestName(moves: WhatIfMove[], chips: Record<number, ChipName>, existing: Draft[]): string {
  const labels: Record<string, string> = { wildcard: "Wildcard", freehit: "Free Hit", bboost: "Bench Boost", "3xc": "Triple Captain" };
  const chip = Object.entries(chips)[0];
  const base = chip ? `${labels[chip[1]]} GW${chip[0]}` : moves.length ? `${moves.length} transfer${moves.length === 1 ? "" : "s"}` : "No transfers";
  let name = base;
  for (let i = 2; existing.some((d) => d.name === name); i++) name = `${base} (${i})`;
  return name;
}
