"use client";

import { useEffect, useState } from "react";
import { track } from "@/lib/analytics";
import { canPrompt, countVisit, isInstalled, onInstallReady, platform, promptInstall, type Platform } from "@/lib/install";

const KEY = "install-hint:v1";

/**
 * From the second visit on, on a phone that hasn't added the app yet: a small card suggesting
 * "Add to Home Screen". Hidden for good once dismissed (on this browser), and never shown
 * alongside the first-visit tips.
 */
export function InstallHint() {
  const [show, setShow] = useState(false);
  const [os, setOs] = useState<Platform>("other");
  const [ready, setReady] = useState(false); // Chrome's own install dialog is available

  useEffect(() => {
    const visits = countVisit();
    let dismissed = true;
    let tipsOpen = false;
    try {
      dismissed = localStorage.getItem(KEY) === "dismissed";
      tipsOpen = localStorage.getItem("tips:v1") !== "seen";
    } catch {
      /* storage blocked: stay hidden */
    }
    const p = platform();
    setOs(p);
    setReady(canPrompt());
    const visible = visits >= 2 && !dismissed && !tipsOpen && !isInstalled() && (p !== "other" || canPrompt());
    setShow(visible);
    if (visible) track("install_hint_shown", { platform: p });
    return onInstallReady(() => setReady(true));
  }, []);

  if (!show) return null;
  const close = () => {
    setShow(false);
    track("install_hint_dismissed", { platform: os });
    try {
      localStorage.setItem(KEY, "dismissed");
    } catch {
      /* private mode */
    }
  };
  const install = async () => {
    if (await promptInstall()) setShow(false);
  };

  return (
    <div className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-3" data-testid="install-hint">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon-192.png" alt="" width={36} height={36} className="shrink-0 rounded-[9px]" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="text-[13.5px] font-semibold">Add the planner to your home screen</div>
        <div className="text-[12.5px] leading-[1.45] text-text2">
          {ready ? (
            "It opens like an app, straight to your team."
          ) : os === "ios" ? (
            <>
              In Safari, tap <ShareIcon /> <b className="text-text">Share</b>, then <b className="text-text">Add to Home Screen</b>.
            </>
          ) : (
            <>
              In Chrome, tap <b className="text-text">⋮</b>, then <b className="text-text">Add to Home screen</b>.
            </>
          )}
        </div>
        <div className="mt-1 flex gap-2">
          {ready && (
            <button type="button" onClick={install} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white">
              Add
            </button>
          )}
          <button type="button" onClick={close} className="rounded-lg bg-pill px-3 py-1.5 text-xs font-semibold text-link">
            {ready ? "Not now" : "Got it"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ShareIcon() {
  return (
    <svg width="13" height="15" viewBox="0 0 13 15" aria-label="the Share icon" className="inline-block align-[-2px]">
      <path d="M6.5 1v8.5M3.5 4l3-3 3 3M2.5 6.5H1.5v7.5h10V6.5h-1" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
