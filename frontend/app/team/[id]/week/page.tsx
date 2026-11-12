"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Countdown } from "@/components/Countdown";
import { FixtureStrip } from "@/components/FixtureStrip";
import { ErrorBox, Loading, ThemeToggle } from "@/components/ui";
import { track } from "@/lib/analytics";
import Link from "next/link";
import { ApiError, getReview, getWeek } from "@/lib/api";
import { gwOf, money, pts, signed } from "@/lib/format";
import type { Player, ReviewResponse, WeekFlag, WeekResponse } from "@/lib/types";

export default function WeekPage() {
  return (
    <Suspense fallback={<Loading message="Loading this week…" />}>
      <WeekScreen />
    </Suspense>
  );
}

const compact = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}m` : n >= 1000 ? `${(n / 1000).toFixed(n >= 100_000 ? 0 : 1)}k` : String(n));

function WeekScreen() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const entry = Number(id);
  const leagueParam = search.get("league");
  const league = leagueParam === null ? null : Number(leagueParam);
  const [data, setData] = useState<WeekResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<ReviewResponse | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    setReview(null);
    getReview(entry, league).then((r) => live && setReview(r)).catch(() => {}); // the page works without it
    getWeek(entry, league)
      .then((d) => {
        if (!live) return;
        setData(d);
        track("week_loaded", { flags: d.flags.filter((f) => f.mine).length });
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Couldn't load this week."));
    return () => {
      live = false;
    };
  }, [entry, league]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading message="Loading this week…" />;

  const p = (pid: number): Player => data.players[pid];
  const n = data.n_rivals;
  const mine = data.flags.filter((f) => f.mine);
  const theirs = data.flags.filter((f) => !f.mine);
  const owned = (pid: number, isMine: boolean) => [isMine ? "yours" : null, n && p(pid).rivals_owned ? `${p(pid).rivals_owned}/${n} rivals` : null].filter(Boolean).join(" · ");
  const squadIds = new Set(mine.map((f) => f.player).concat(data.dream_team.filter((d) => d.mine).map((d) => d.player)));

  return (
    <main className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <h1 className="m-0 font-display text-[26px] font-bold">This week · GW{data.gw}</h1>
        <ThemeToggle />
      </div>
      <Countdown gw={data.gw} deadline={data.deadline} />

      {data.captains.length > 0 && (
        <Card title={`Captain for GW${data.gw}`} sub="Your best options. Points shown before doubling." testid="week-captains">
          {data.captains.map((c, i) => (
            <div key={c.player} className="flex items-center justify-between gap-3 border-t border-line pt-2 first:border-t-0 first:pt-0">
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-[13.5px] font-semibold">
                  {p(c.player).doubtful ? "! " : ""}
                  {p(c.player).name}
                  {i === 0 && <span className="ml-1.5 rounded-full bg-cap-bg px-2 py-0.5 text-[10.5px] font-semibold text-why-label">Top pick</span>}
                </span>
                <span className="truncate text-[11.5px] text-text3">
                  {gwOf(p(c.player), data.gw).fixture}
                  {n ? ` · ${c.rivals_captained}/${n} rivals captained him last week` : ""}
                </span>
              </div>
              <span className="shrink-0 font-display text-[15px] font-bold">{pts(c.xpts)}</span>
            </div>
          ))}
        </Card>
      )}

      {review && <ReviewCard review={review} />}

      <Link
        href={`/team/${entry}/compare${league !== null ? `?league=${league}` : ""}`}
        onClick={() => track("compare_opened", { from: "week" })}
        className="flex h-11 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-[14px] font-semibold no-underline"
      >
        Compare players
      </Link>

      <Card title="Injuries and suspensions" testid="week-flags">
        {mine.length === 0 ? (
          <div className="text-[13px] text-text2">Nobody in your squad is flagged.</div>
        ) : (
          mine.map((f) => <FlagRow key={f.player} flag={f} player={p(f.player)} note={n && f.rivals_owned ? `${f.rivals_owned}/${n} rivals also own him` : ""} />)
        )}
        {theirs.length > 0 && (
          <>
            <div className="mt-1 text-xs font-semibold text-text3">YOUR RIVALS&apos; PLAYERS</div>
            {theirs.map((f) => (
              <FlagRow key={f.player} flag={f} player={p(f.player)} note={`${f.rivals_owned}/${n} rivals own him`} />
            ))}
          </>
        )}
        {!data.rivals_ready && <div className="text-xs text-text3">Your rivals&apos; teams are still loading. Come back in a moment for their flags.</div>}
      </Card>

      <Card title="Most transferred this week" sub="All FPL managers" testid="week-transfers">
        <div className="grid grid-cols-2 gap-3">
          {([["IN", data.top_in, "text-good"], ["OUT", data.top_out, "text-out"]] as const).map(([label, list, colour]) => (
            <div key={label} className="flex min-w-0 flex-col gap-1.5">
              <div className={`text-[11px] font-semibold ${colour}`}>{label}</div>
              {list.map((m) => (
                <div key={m.player} className="flex min-w-0 flex-col">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[13px] font-semibold">{p(m.player).name}</span>
                    <span className="shrink-0 text-xs text-text2">{compact(m.count)}</span>
                  </div>
                  <span className="truncate text-[11.5px] text-text3">
                    {p(m.player).club} · {money(p(m.player).price)}
                    {owned(m.player, p(m.player).sell_price !== null) ? ` · ${owned(m.player, p(m.player).sell_price !== null)}` : ""}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Fixture ticker" sub="Easiest run first · UPPER CASE home, lower case away" testid="week-ticker">
        <div className="flex items-center gap-2 text-[9.5px] text-text3">
          <span className="w-9 shrink-0" />
          <div className="flex flex-1 gap-0.5">
            {data.ticker[0]?.gws.map((g) => (
              <span key={g.gw} className="flex-1 text-center">GW{g.gw}</span>
            ))}
          </div>
        </div>
        {data.ticker.map((row) => (
          <div key={row.club} className="flex items-center gap-2" title={row.name}>
            <span className="w-9 shrink-0 text-[11.5px] font-semibold">{row.club}</span>
            <div className="flex-1">
              <FixtureStrip gws={row.gws.map((g) => ({ ...g, xpts: 0 }))} labels={false} />
            </div>
          </div>
        ))}
      </Card>

      {data.dream_team.length > 0 && (
        <Card title={`Team of the week · GW${data.last_gw}`} sub="FPL's highest scorers last gameweek" testid="week-dream">
          {data.dream_team.map((d) => (
            <div key={d.player} className="flex items-baseline justify-between gap-2 text-[13px]">
              <span className="min-w-0 truncate">
                <span className="text-text3">{p(d.player).position}</span> <span className="font-semibold">{p(d.player).name}</span>{" "}
                <span className="text-[11.5px] text-text3">
                  {p(d.player).club}
                  {owned(d.player, d.mine) ? ` · ${owned(d.player, d.mine)}` : ""}
                </span>
              </span>
              <span className={`shrink-0 font-semibold ${d.mine || squadIds.has(d.player) ? "text-good" : ""}`}>{d.points} pts</span>
            </div>
          ))}
        </Card>
      )}
      <div className="text-center text-xs text-text3">From FPL&apos;s public data. Transfer counts are for the whole game, not your league.</div>
    </main>
  );
}

function Card({ title, sub, testid, children }: { title: string; sub?: string; testid: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-3.5" data-testid={testid}>
      <div className="flex flex-col gap-0.5">
        <h2 className="m-0 font-display text-base font-bold">{title}</h2>
        {sub && <div className="text-[11.5px] text-text3">{sub}</div>}
      </div>
      {children}
    </section>
  );
}

function FlagRow({ flag, player, note }: { flag: WeekFlag; player: Player; note: string }) {
  const out = flag.chance === 0;
  return (
    <div className="flex flex-col gap-0.5 border-t border-line pt-2 first:border-t-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[13.5px] font-semibold">
          {player.name} <span className="text-[11.5px] font-normal text-text3">{player.club} · {player.position}</span>
        </span>
        {flag.chance !== null && <span className={`shrink-0 text-xs font-semibold ${out ? "text-bad" : "text-warn-text"}`}>{out ? "Out" : `${flag.chance}% to play`}</span>}
      </div>
      {flag.news && <div className="text-[12.5px] leading-[1.4] text-text2">{flag.news}</div>}
      {flag.ban_at !== null && (
        <div className="text-[12.5px] leading-[1.4] text-text2">
          {flag.yellow_cards} yellow cards: one more brings a {flag.ban_at === 5 ? "one" : "two"}-match ban.
        </div>
      )}
      {note && <div className="text-[11.5px] text-text3">{note}</div>}
    </div>
  );
}

/** Last gameweek against the model's projection, and against each rival. */
function ReviewCard({ review }: { review: ReviewResponse }) {
  const title = `How GW${review.gw} went`;
  if (!review.available) {
    return (
      <Card title={title} testid="week-review">
        <div className="text-[13px] text-text2">{review.message}</div>
      </Card>
    );
  }
  const name = (pid: number) => review.players[pid]?.name ?? "?";
  const diff = review.points - review.projected;
  const cap = review.captain;
  const best = review.best_captain;
  const movers = (list: ReviewResponse["over"]) => list.map((m) => `${name(m.player)} ${m.points} (${pts(m.projected)})`).join(", ");
  return (
    <Card title={title} sub="Points scored, with our projection from before the deadline in brackets" testid="week-review">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] text-text2">
          You scored{review.hit_cost ? ` (after a −${review.hit_cost} hit)` : ""}
        </span>
        <span>
          <span className="font-display text-xl font-bold">{review.points}</span>{" "}
          <span className={`text-xs font-semibold ${diff >= 0 ? "text-good" : "text-bad"}`}>
            {signed(diff)} vs projected {pts(review.projected)}
          </span>
        </span>
      </div>
      {cap && (
        <div className="text-[13px] leading-[1.45]">
          <b>Captain:</b> {name(cap.player)} scored {cap.points} ({pts(cap.projected)}).
          {best && best.player !== cap.player && best.points > cap.points ? ` Your top scorer was ${name(best.player)} with ${best.points}.` : best && best.player === cap.player ? " He was your top scorer." : ""}
        </div>
      )}
      {review.over.length > 0 && (
        <div className="text-[13px] leading-[1.45]">
          <b className="text-good">Beat the projection:</b> {movers(review.over)}
        </div>
      )}
      {review.under.length > 0 && (
        <div className="text-[13px] leading-[1.45]">
          <b className="text-bad">Fell short:</b> {movers(review.under)}
        </div>
      )}
      {review.rivals.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-line pt-2">
          <div className="text-xs font-semibold text-text3">AGAINST YOUR RIVALS</div>
          {review.rivals.map((r) => (
            <div key={r.entry_name + r.name} className="flex items-baseline justify-between gap-2 text-[13px]">
              <span className="min-w-0 truncate">
                {r.name} <span className="text-[11.5px] text-text3">scored {r.points}</span>
              </span>
              <span className={`shrink-0 font-semibold ${r.swing > 0 ? "text-good" : r.swing < 0 ? "text-bad" : ""}`}>
                {r.swing > 0 ? `You gained ${r.swing}` : r.swing < 0 ? `You lost ${-r.swing}` : "Level"}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
