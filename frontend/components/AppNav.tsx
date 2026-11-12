"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { track } from "@/lib/analytics";
import { endDemo, isDemo, loadNav, type NavContext } from "@/lib/nav";

type Tab = "team" | "plans" | "whatif" | "drafts" | "week";

/** Which team's screens we're on, read from the address ("/team/123/…" or "/plans?team=123"). */
function useTeam(): { team: number | null; tab: Tab; league: number | null; search: string } {
  const pathname = usePathname();
  const search = useSearchParams();
  const fromPath = pathname.match(/^\/team\/(\d+)/)?.[1];
  const onPlans = pathname.startsWith("/plans");
  const team = fromPath ? Number(fromPath) : onPlans && search.get("team") ? Number(search.get("team")) : null;
  const tab: Tab = onPlans ? "plans" : pathname.includes("/what-if") ? "whatif" : pathname.includes("/drafts") ? "drafts" : pathname.endsWith("/week") ? "week" : "team";
  const league = search.get("league");
  return { team, tab, league: league === null ? null : Number(league), search: search.toString() };
}

/** "You're viewing a sample team" strip, shown at the top of every screen in the demo. */
export function DemoBanner() {
  const { team } = useTeam();
  const pathname = usePathname();
  const [demo, setDemo] = useState(false);
  useEffect(() => setDemo(team !== null && isDemo(team)), [team, pathname]);
  if (!demo) return null;
  return (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-xl bg-cap-bg px-3 py-2 text-[12.5px]" data-testid="demo-banner">
      <span className="text-text2">
        <b className="text-text">Sample team.</b> This is a real team and mini-league.
      </span>
      <Link href="/" onClick={() => { endDemo(); track("demo_ended"); }} className="shrink-0 font-semibold no-underline">
        Use my team →
      </Link>
    </div>
  );
}

/** The bottom tab bar: My team, Plans, What-if, Drafts, This week. Only on a team's screens. */
export function AppNav() {
  const { team, tab, league: urlLeague, search } = useTeam();
  const pathname = usePathname();
  const [ctx, setCtx] = useState<NavContext | null>(null);
  useEffect(() => setCtx(team === null ? null : loadNav(team)), [team, pathname, search]);
  if (team === null) return null;

  const league = urlLeague ?? ctx?.league ?? null;
  const strategy = ctx?.strategy ?? "balanced";
  const lq = league !== null ? `league=${league}` : "";
  const tabs: { key: Tab; label: string; href: string; icon: React.ReactNode }[] = [
    { key: "team", label: "My team", href: `/team/${team}${lq ? `?${lq}` : ""}`, icon: <path d="M10 3.5l3 1.8 3-1.3 1.5 4-2.5 1.2V16h-10V9.2L2.5 8 4 4l3 1.3 3-1.8z" /> },
    {
      key: "plans",
      label: "Plans",
      href: tab === "plans" ? `${pathname.replace(/\/\d+$/, "")}?${search}` : `/plans?team=${team}${lq ? `&${lq}` : ""}&strategy=${strategy}&horizon=4&hits=0`,
      icon: <path d="M3 7h11m-3-3.5L14.5 7 11 10.5M17 13H6m3-3.5L5.5 13 9 16.5" />,
    },
    { key: "whatif", label: "What-if", href: `/team/${team}/what-if?${lq ? `${lq}&` : ""}strategy=${strategy}`, icon: <path d="M4 16l1-4 8.5-8.5 3 3L8 15l-4 1zM11.5 5.5l3 3" /> },
    { key: "drafts", label: "Drafts", href: `/team/${team}/drafts${lq ? `?${lq}` : ""}`, icon: <path d="M5.5 3h9v14l-4.5-3-4.5 3V3z" /> },
    { key: "week", label: "This week", href: `/team/${team}/week${lq ? `?${lq}` : ""}`, icon: <path d="M3.5 5.5h13v11h-13zM3.5 8.5h13M7 3.5v3M13 3.5v3" /> },
  ];
  return (
    <>
      <div className="h-[72px] shrink-0" aria-hidden="true" />
      <nav
        aria-label="Sections"
        data-testid="app-nav"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      >
        <div className="mx-auto flex w-full max-w-[440px] px-2">
          {tabs.map((t) => (
            <Link
              key={t.key}
              href={t.href}
              aria-current={t.key === tab ? "page" : undefined}
              onClick={() => t.key !== tab && track("nav_tab", { to: t.key, from: tab })}
              className={`flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold no-underline ${t.key === tab ? "text-link" : "text-text3"}`}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {t.icon}
              </svg>
              {t.label}
            </Link>
          ))}
        </div>
      </nav>
    </>
  );
}
