"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <rect x="1" y="1" width="26" height="26" rx="7" fill="#1F7A4D" />
        <line x1="14" y1="1" x2="14" y2="27" stroke="#FFFFFF" strokeWidth="1.5" />
        <circle cx="14" cy="14" r="5" fill="none" stroke="#FFFFFF" strokeWidth="1.5" />
      </svg>
      <div className="font-display text-[17px] font-bold">Mini-League Planner</div>
    </div>
  );
}

export function ThemeToggle() {
  const [light, setLight] = useState(false);
  useEffect(() => setLight(document.documentElement.dataset.theme === "light"), []);
  const toggle = () => {
    const next = !light;
    setLight(next);
    if (next) document.documentElement.dataset.theme = "light";
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem("theme", next ? "light" : "dark");
    } catch {
      /* private mode */
    }
  };
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={light ? "Switch to dark mode" : "Switch to light mode"}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface text-text2"
    >
      {light ? (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z" fill="currentColor" /></svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3.2" fill="currentColor" /><g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3 3l1.1 1.1M11.9 11.9 13 13M3 13l1.1-1.1M11.9 4.1 13 3" /></g></svg>
      )}
    </button>
  );
}

export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="flex min-h-6 items-center gap-1 text-[13px] font-semibold text-link no-underline">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3L5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      {label}
    </Link>
  );
}

export function TopBar({ left }: { left: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      {left}
      <ThemeToggle />
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "sm",
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div className="flex gap-0.5 rounded-lg bg-seg p-[3px]" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={o.key === value}
          onClick={() => onChange(o.key)}
          className={`whitespace-nowrap rounded-md font-semibold ${size === "md" ? "h-8 px-3.5 text-[13px]" : "h-7 px-2.5 text-xs"} ${
            o.key === value ? "bg-seg-on text-text" : "bg-transparent text-text3"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Loading({ message }: { message: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center text-sm text-text2" role="status">
      <svg className="spinner" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <circle cx="14" cy="14" r="11" fill="none" stroke="var(--border)" strokeWidth="3" />
        <path d="M14 3a11 11 0 0 1 11 11" fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {message}
    </div>
  );
}

export function ErrorBox({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div role="alert" className="flex flex-col gap-2 rounded-xl bg-warn-bg px-3.5 py-3 text-[13px] leading-snug text-warn-text">
      <span>{message}</span>
      {action}
    </div>
  );
}

export function Facts({ facts }: { facts: string[] }) {
  return (
    <div className="flex flex-col gap-1 text-center text-xs leading-snug text-text3">
      {facts.map((f) => (
        <div key={f}>{f}</div>
      ))}
    </div>
  );
}

export function Tile({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-xl border border-line bg-surface px-2.5 py-2">
      <div className="text-[11.5px] text-text3">{label}</div>
      <div className={`font-display text-xl font-bold ${tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : ""}`}>{value}</div>
    </div>
  );
}
