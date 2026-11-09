"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { reportError, scrubUrl, startAnalytics, track } from "@/lib/analytics";

/** Starts tracking (if configured) and records a scrubbed page view on each navigation. */
export function Analytics() {
  const pathname = usePathname();
  useEffect(() => {
    startAnalytics();
    // Crashes nobody caught: report them (scrubbed) so we hear about what breaks.
    const onError = (e: ErrorEvent) => reportError("crash", e.message, { page: scrubUrl(window.location.pathname) });
    const onRejection = (e: PromiseRejectionEvent) =>
      reportError("crash", e.reason instanceof Error ? e.reason.message : String(e.reason), { page: scrubUrl(window.location.pathname) });
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  useEffect(() => {
    track("$pageview", { $current_url: scrubUrl(window.location.href), page: scrubUrl(pathname) });
  }, [pathname]);
  return null;
}
