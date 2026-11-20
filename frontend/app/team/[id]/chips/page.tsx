"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { saveIcs } from "@/components/AddToCalendar";
import { ChipSquadView } from "@/components/ChipSquad";
import { Countdown } from "@/components/Countdown";
import { usePlayerInfo } from "@/components/PlayerInfo";
import { CardsSkeleton } from "@/components/Skeleton";
import { ErrorBox, Facts, Loading, ThemeToggle } from "@/components/ui";
import { Why } from "@/components/Why";
import { track } from "@/lib/analytics";
import { ApiError, getChipReason, getChips } from "@/lib/api";
import { loadNav } from "@/lib/nav";
import { pts } from "@/lib/format";
import type { ChipOutlook, ChipReason, ChipsResponse, Player } from "@/lib/types";

export default function ChipsPage() {
  return (
    <Suspense fallback={<Loading message="Planning your chips…" />}>
      <ChipsScreen />
    </Suspense>
  );
}

// The query name Plans uses for a chosen week of each chip.
const PLAN_PARAM: Record<string, string> = { bboost: "bboost", freehit: "freehit", "3xc": "tcap" };
const WHAT_IT_ADDS: Record<string, string> = {
  bboost: "Your bench's projected points that week",
  "3xc": "Your captain's projected points once more",
  freehit: "A one-week squad's projected gain over your own best lineup",
};

function ChipsScreen() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const entry = Number(id);
  const leagueParam = search.get("league");
  const league = leagueParam === null ? null : Number(leagueParam);
  const [data, setData] = useState<ChipsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const info = usePlayerInfo(0, `/team/${entry}/compare?${league !== null ? `league=${league}&` : ""}p=`);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    getChips(entry, league)
      .then((d) => {
        if (!live) return;
        setData(d);
        track("chips_loaded", {
          chips: d.chips.length,
          play_now: d.chips.filter((c) => c.play_now).map((c) => c.name).join(",") || "none",
        });
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Couldn't plan your chips."));
    return () => {
      live = false;
    };
  }, [entry, league]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <CardsSkeleton rows={3} message="Planning your chips…" />;

  const first = data.gws[0];
  return (
    <main className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <h1 className="m-0 font-display text-[26px] font-bold">Chips · GW{first}</h1>
        <ThemeToggle />
      </div>
      {data.deadline && <Countdown gw={first} deadline={data.deadline} />}

      {data.chips.length === 0 ? (
        <section className="rounded-2xl border border-line bg-surface p-3.5 text-[13.5px] text-text2" data-testid="chips-none">
          You have no chips to play from GW{first} to GW{data.gws[data.gws.length - 1]}.
        </section>
      ) : (
        data.chips.map((c) => <ChipCard key={`${c.name}-${c.start}`} chip={c} data={data} entry={entry} league={league} onOpen={info.open} />)
      )}

      <div className="rounded-xl bg-pill px-3 py-2.5 text-[12.5px] leading-[1.45] text-text2" data-testid="chips-fixtures">
        {data.fixture_note}
      </div>

      {data.later.length > 0 && (
        <div className="text-[12.5px] leading-[1.45] text-text3">
          Also left: {data.later.map((c) => `${c.label} (GW${c.start}–${c.stop})`).join(", ")}. These are ranked once their weeks come into view.
        </div>
      )}

      <Facts facts={data.facts} />
      {info.sheet}
    </main>
  );
}

function ChipCard({ chip, data, entry, league, onOpen }: {
  chip: ChipOutlook; data: ChipsResponse; entry: number; league: number | null; onOpen: (p: Player) => void;
}) {
  const [reason, setReason] = useState<ChipReason | null>(null);
  const [selected, setSelected] = useState<number | null>(chip.best_gw); // the week whose squad is shown
  const ranked = chip.ranked && chip.best_gw !== null;
  useEffect(() => {
    if (!ranked) return;
    let live = true;
    getChipReason(entry, league, chip.name).then((r) => {
      if (!live) return;
      setReason(r);
      track(r.status === "ok" ? "chip_reason_shown" : "chip_reason_missing", { chip: chip.name, status: r.status });
    });
    return () => {
      live = false;
    };
  }, [entry, league, chip.name, ranked]);

  const first = data.gws[0];
  const best = chip.weeks.find((w) => w.gw === chip.best_gw) ?? null;
  const week = chip.weeks.find((w) => w.gw === selected) ?? best;
  const target = week?.gw ?? chip.best_gw; // reminders and plans follow the week you're looking at
  const max = Math.max(0.1, ...chip.weeks.map((w) => w.xpts));
  const badge = !ranked
    ? { text: "Your call", tone: "bg-pill text-text2" }
    : !chip.advised
      ? { text: `Best projected: GW${chip.best_gw}`, tone: "bg-pill text-text" }
      : chip.play_now
        ? { text: "Play this week", tone: "bg-good/15 text-good" }
        : { text: `Hold · best GW${chip.best_gw}`, tone: "bg-cap-bg text-why-label" };

  const strategy = loadNav(entry)?.strategy ?? "balanced";
  const inReach = target !== null && target <= first + 4 && chip.name in PLAN_PARAM;
  const planHref = inReach
    ? `/plans?team=${entry}${league !== null ? `&league=${league}` : ""}&strategy=${strategy}` +
      `&horizon=${Math.min(5, Math.max(4, target! - first + 1))}&hits=0&${PLAN_PARAM[chip.name]}=${target}`
    : null;
  const remind = () => {
    const gw = data.gameweeks.find((g) => g.id === target);
    if (!gw) return;
    saveIcs([{ gw: gw.id, deadline: gw.deadline, note: `play your ${chip.label}` }], `fpl-${chip.name}-gw${gw.id}.ics`);
    track("chip_reminder_added", { chip: chip.name, weeks_ahead: gw.id - first });
  };

  return (
    <section className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface p-3.5" data-testid={`chip-${chip.name}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="m-0 font-display text-base font-bold">{chip.label}</h2>
          <div className="text-[11.5px] text-text3">
            {ranked ? WHAT_IT_ADDS[chip.name] : `Play it by GW${chip.stop}`}
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11.5px] font-semibold ${badge.tone}`} data-testid="chip-verdict">
          {badge.text}
        </span>
      </div>

      {ranked && (
        <div className="flex items-end gap-1" role="group" aria-label={`Projected points the ${chip.label} adds each week. Tap a week to see its squad.`} data-testid="chip-weeks">
          {chip.weeks.map((w) => {
            const isBest = w.gw === chip.best_gw;
            const isClose = chip.close.includes(w.gw);
            const odd = w.blanks.length > 0 || w.doubles.length > 0;
            const isSelected = w.gw === week?.gw;
            return (
              <button
                key={w.gw}
                type="button"
                aria-pressed={isSelected}
                aria-label={`GW${w.gw}: ${pts(w.xpts)}`}
                onClick={() => {
                  setSelected(w.gw);
                  track("chip_week_selected", { chip: chip.name, weeks_ahead: w.gw - first, best: isBest });
                }}
                className={`flex min-w-0 flex-1 flex-col items-center gap-1 rounded-md pb-0.5 pt-1 ${isSelected ? "bg-pill" : ""}`}
              >
                <span className={`text-[10.5px] tabular-nums ${isBest ? "font-bold text-text" : "text-text3"}`}>{pts(w.xpts)}</span>
                <div className="flex h-16 w-full items-end">
                  <div
                    className={`w-full rounded-t ${isBest ? "bg-accent" : isClose ? "bg-accent/45" : "bg-line"}`}
                    style={{ height: `${Math.max(4, (w.xpts / max) * 100)}%` }}
                  />
                </div>
                <span className={`text-[10px] ${w.gw === first ? "font-bold text-text" : "text-text3"}`}>
                  {w.gw === first ? "Now" : `GW${w.gw}`}
                </span>
                {odd && (
                  <span className="text-[9px] font-semibold text-warn-text" title={[...(w.doubles.length ? [`Doubles: ${w.doubles.join(", ")}`] : []), ...(w.blanks.length ? [`Blanks: ${w.blanks.join(", ")}`] : [])].join(" · ")}>
                    {w.doubles.length ? "DGW" : "BGW"}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      <div className="flex flex-col gap-1.5 text-[13px] leading-[1.45] text-text2" data-testid="chip-lines">
        {chip.lines.map((l) => (
          <p key={l} className="m-0">{l}</p>
        ))}
      </div>

      {ranked && <Why explanation={reason} label={`Why GW${chip.best_gw}`} />}

      {ranked && week?.squad && (
        <ChipSquadView
          chip={chip.name}
          week={week}
          first={first}
          players={data.players}
          clubs={data.clubs}
          team={entry}
          league={league}
          strategy={strategy}
          onOpen={onOpen}
        />
      )}

      {ranked && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-2.5">
          {planHref && (
            <Link
              href={planHref}
              onClick={() => track("chip_plan_opened", { chip: chip.name, weeks_ahead: target! - first })}
              className="text-[13px] font-semibold no-underline"
              data-testid="chip-plan-link"
            >
              Plan around GW{target} →
            </Link>
          )}
          {!planHref && target !== null && chip.name in PLAN_PARAM && (
            <span className="text-[12px] text-text3">Plans reach GW{first + 4}; you can plan around GW{target} from GW{target - 4}.</span>
          )}
          <button type="button" onClick={remind} className="text-[13px] font-semibold text-link" data-testid="chip-remind">
            Remind me before GW{target}
          </button>
        </div>
      )}
    </section>
  );
}
