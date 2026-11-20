"use client";

import { track } from "@/lib/analytics";

const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

export interface CalendarDeadline {
  gw: number;
  deadline: string;
  note?: string; // e.g. "play your Bench Boost": goes in the title and the reminders
}

/** A calendar file (.ics) with one event per deadline, each with reminders a day and 3 hours before. */
export function deadlinesIcs(deadlines: CalendarDeadline[], url: string, now = new Date()): string {
  const events = deadlines.map(({ gw, deadline, note }) => {
    const what = note ? `FPL GW${gw}: ${note}` : `FPL GW${gw} deadline`;
    const end = new Date(deadline);
    const start = new Date(end.getTime() - 30 * 60_000);
    return [
      "BEGIN:VEVENT",
      `UID:fpl-gw${gw}-${note ? note.replace(/[^a-z]+/gi, "-").toLowerCase() : "deadline"}@mini-league-planner`,
      `DTSTAMP:${stamp(now)}`,
      `DTSTART:${stamp(start)}`,
      `DTEND:${stamp(end)}`,
      `SUMMARY:${what}`,
      `DESCRIPTION:${note ? `Before the GW${gw} deadline: ${note}.` : `Make your GW${gw} transfers before the deadline.`} Plan them: ${url}`,
      `URL:${url}`,
      "BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${what} (deadline tomorrow)`, "TRIGGER:-P1D", "END:VALARM",
      "BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${what} (deadline in 3 hours)`, "TRIGGER:-PT3H", "END:VALARM",
      "END:VEVENT",
    ].join("\r\n");
  });
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mini-League Planner//FPL deadlines//EN", "CALSCALE:GREGORIAN", ...events, "END:VCALENDAR"].join("\r\n") + "\r\n";
}

/** Hands the browser a calendar file to save or open. */
export function saveIcs(deadlines: CalendarDeadline[], filename: string): void {
  const blob = new Blob([deadlinesIcs(deadlines, window.location.origin)], { type: "text/calendar" });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

export function AddToCalendar({ deadlines, className = "" }: { deadlines: CalendarDeadline[]; className?: string }) {
  const upcoming = deadlines.filter((d) => new Date(d.deadline).getTime() > Date.now());
  if (upcoming.length === 0) return null;
  const save = () => {
    saveIcs(upcoming, "fpl-deadlines.ics");
    track("calendar_added", { deadlines: upcoming.length });
  };
  return (
    <button type="button" onClick={save} data-testid="add-calendar" className={`text-[13px] font-semibold text-link ${className}`}>
      Add deadlines to calendar
    </button>
  );
}
