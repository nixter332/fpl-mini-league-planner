"use client";

import { track } from "@/lib/analytics";

const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

/** A calendar file (.ics) with one event per deadline, each with reminders a day and 3 hours before. */
export function deadlinesIcs(deadlines: { gw: number; deadline: string }[], url: string, now = new Date()): string {
  const events = deadlines.map(({ gw, deadline }) => {
    const end = new Date(deadline);
    const start = new Date(end.getTime() - 30 * 60_000);
    return [
      "BEGIN:VEVENT",
      `UID:fpl-gw${gw}-deadline@mini-league-planner`,
      `DTSTAMP:${stamp(now)}`,
      `DTSTART:${stamp(start)}`,
      `DTEND:${stamp(end)}`,
      `SUMMARY:FPL GW${gw} deadline`,
      `DESCRIPTION:Make your GW${gw} transfers before the deadline. Plan them: ${url}`,
      `URL:${url}`,
      "BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:FPL GW${gw} deadline tomorrow`, "TRIGGER:-P1D", "END:VALARM",
      "BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:FPL GW${gw} deadline in 3 hours`, "TRIGGER:-PT3H", "END:VALARM",
      "END:VEVENT",
    ].join("\r\n");
  });
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mini-League Planner//FPL deadlines//EN", "CALSCALE:GREGORIAN", ...events, "END:VCALENDAR"].join("\r\n") + "\r\n";
}

export function AddToCalendar({ deadlines, className = "" }: { deadlines: { gw: number; deadline: string }[]; className?: string }) {
  const upcoming = deadlines.filter((d) => new Date(d.deadline).getTime() > Date.now());
  if (upcoming.length === 0) return null;
  const save = () => {
    const blob = new Blob([deadlinesIcs(upcoming, window.location.origin)], { type: "text/calendar" });
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = "fpl-deadlines.ics";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 10_000);
    track("calendar_added", { deadlines: upcoming.length });
  };
  return (
    <button type="button" onClick={save} data-testid="add-calendar" className={`text-[13px] font-semibold text-link ${className}`}>
      Add deadlines to calendar
    </button>
  );
}
