// "Add to Home Screen" support. Chrome on Android offers an install prompt we can trigger from a
// button (the `beforeinstallprompt` event, which fires once, early, so it's caught here at load).
// iPhones have no such event: we show the Share → Add to Home Screen steps instead.

import { track } from "./analytics";

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // we show our own, gentler hint
    deferred = e as InstallPromptEvent;
    listeners.forEach((l) => l());
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    track("app_installed");
  });
}

/** Call back when Chrome's install prompt becomes available. */
export function onInstallReady(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const canPrompt = () => deferred !== null;

/** Opens Chrome's install dialog. */
export async function promptInstall(): Promise<boolean> {
  if (!deferred) return false;
  const e = deferred;
  deferred = null;
  await e.prompt();
  const { outcome } = await e.userChoice;
  track("install_prompt", { outcome });
  return outcome === "accepted";
}

/** Already opened from the home screen? */
export function isInstalled(): boolean {
  return window.matchMedia?.("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
}

export type Platform = "ios" | "android" | "other";

export function platform(): Platform {
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return "ios";
  if (/Android/.test(ua)) return "android";
  return "other";
}

const VISITS = "visits:v1";

/** Counts visits (once per browser session) and returns the total. */
export function countVisit(): number {
  try {
    let n = Number(localStorage.getItem(VISITS) ?? 0) || 0;
    if (!sessionStorage.getItem(VISITS)) {
      n += 1;
      localStorage.setItem(VISITS, String(n));
      sessionStorage.setItem(VISITS, "1");
    }
    return n;
  } catch {
    return 0;
  }
}
