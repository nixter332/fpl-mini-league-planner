"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { FixtureStrip } from "@/components/FixtureStrip";
import { PriceMove } from "@/components/PriceMove";
import { BackLink, ErrorBox, Loading, ThemeToggle } from "@/components/ui";
import { track } from "@/lib/analytics";
import { ApiError, getAllPlayers } from "@/lib/api";
import { money, pts } from "@/lib/format";
import type { Player, PlayersResponse } from "@/lib/types";

const MAX = 3;

export default function ComparePage() {
  return (
    <Suspense fallback={<Loading message="Loading players…" />}>
      <CompareScreen />
    </Suspense>
  );
}

function CompareScreen() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const entry = Number(id);
  const leagueParam = search.get("league");
  const league = leagueParam === null ? null : Number(leagueParam);
  const ids = useMemo(() => (search.get("p") ?? "").split(",").map(Number).filter((n) => n > 0).slice(0, MAX), [search]);
  const [data, setData] = useState<PlayersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let live = true;
    getAllPlayers(entry, league)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Couldn't load players."));
    return () => {
      live = false;
    };
  }, [entry, league]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading message="Loading players…" />;

  const lq = league !== null ? `league=${league}` : "";
  const set = (next: number[]) => router.replace(`/team/${entry}/compare?${lq ? `${lq}&` : ""}p=${next.join(",")}`);
  const chosen = ids.map((pid) => data.players[pid]).filter(Boolean) as Player[];
  const total = (p: Player) => p.gws.reduce((sum, g) => sum + g.xpts, 0);
  const q = query.trim().toLowerCase();
  const position = chosen[0]?.position;
  const results = q
    ? Object.values(data.players)
        .filter((p) => !ids.includes(p.id) && (p.name.toLowerCase().includes(q) || p.club.toLowerCase().includes(q)))
        .sort((a, b) => Number(b.position === position) - Number(a.position === position) || total(b) - total(a))
        .slice(0, 8)
    : [];
  const nRivals = Math.max(0, ...Object.values(data.players).map((p) => p.rivals_owned));

  const rows: { label: string; value: (p: Player) => number; show: (p: Player) => React.ReactNode; best: "high" | "low" | null }[] = [
    { label: "Price", value: (p) => p.price, show: (p) => <>{money(p.price)}<PriceMove change={p.price_change} /></>, best: "low" },
    { label: `GW${data.gws[0]} xPts`, value: (p) => p.gws[0]?.xpts ?? 0, show: (p) => pts(p.gws[0]?.xpts ?? 0), best: "high" },
    { label: `Next ${data.gws.length} GWs xPts`, value: total, show: (p) => pts(total(p)), best: "high" },
    { label: "xPts per £m", value: (p) => total(p) / (p.price / 10), show: (p) => (total(p) / (p.price / 10)).toFixed(1), best: "high" },
    { label: "Rivals own", value: (p) => p.rivals_owned, show: (p) => (nRivals ? String(p.rivals_owned) : "—"), best: null },
  ];
  const isBest = (row: (typeof rows)[number], p: Player) => {
    if (!row.best || chosen.length < 2) return false;
    const values = chosen.map(row.value);
    const target = row.best === "high" ? Math.max(...values) : Math.min(...values);
    return row.value(p) === target && values.filter((v) => v === target).length === 1;
  };

  return (
    <main className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <BackLink href={`/team/${entry}${lq ? `?${lq}` : ""}`} label="My team" />
        <ThemeToggle />
      </div>
      <h1 className="m-0 font-display text-[26px] font-bold">Compare players</h1>

      {chosen.length < MAX && (
        <div className="flex flex-col gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={chosen.length ? "Add another player (name or club)" : "Search a player (name or club)"}
            aria-label="Search players"
            className="h-11 rounded-[10px] border border-input-line bg-input px-3 text-sm text-text placeholder:text-text3"
          />
          {results.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                set([...ids, p.id]);
                setQuery("");
                track("compare_added", { count: ids.length + 1 });
              }}
              className="flex items-center justify-between gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-left"
              data-testid="compare-result"
            >
              <span className="min-w-0 truncate text-sm font-semibold">
                {p.name} <span className="text-[11.5px] font-normal text-text3">{p.club} · {p.position} · {money(p.price)}</span>
              </span>
              <span className="shrink-0 text-xs text-text2">{pts(total(p))} xPts</span>
            </button>
          ))}
        </div>
      )}

      {chosen.length === 0 ? (
        <div className="rounded-2xl border border-line bg-surface p-3.5 text-[13px] text-text2">Search for up to {MAX} players to see them side by side.</div>
      ) : (
        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-3.5" data-testid="compare-table">
          <div className="grid gap-x-2 gap-y-2 text-[13px]" style={{ gridTemplateColumns: `minmax(64px, 0.8fr) repeat(${chosen.length}, minmax(0, 1fr))` }}>
            <span />
            {chosen.map((p) => (
              <div key={p.id} className="flex min-w-0 flex-col">
                <span className="truncate font-semibold">{p.name}</span>
                <span className="truncate text-[11.5px] text-text3">{p.club} · {p.position}</span>
                <button type="button" onClick={() => set(ids.filter((x) => x !== p.id))} className="self-start text-[11.5px] text-text3 underline" aria-label={`Remove ${p.name}`}>
                  Remove
                </button>
              </div>
            ))}
            {rows.map((row) => (
              <div key={row.label} className="contents">
                <span className="border-t border-line pt-2 text-[11.5px] text-text3">{row.label}</span>
                {chosen.map((p) => (
                  <span key={p.id} className={`border-t border-line pt-2 font-semibold ${isBest(row, p) ? "text-good" : ""}`}>{row.show(p)}</span>
                ))}
              </div>
            ))}
          </div>
          {chosen.map((p) => (
            <div key={p.id} className="flex flex-col gap-1">
              <div className="text-[11.5px] text-text3">
                <b className="text-text2">{p.name}</b>
                {p.news ? ` · ${p.news}` : ""}
              </div>
              <FixtureStrip gws={p.gws} />
            </div>
          ))}
          <div className="text-[11.5px] text-text3">Green marks the best of the players shown. xPts are our model&apos;s expected points.</div>
        </div>
      )}
    </main>
  );
}
