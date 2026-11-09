"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { scrubUrl, startAnalytics, track } from "@/lib/analytics";

/** Starts tracking (if configured) and records a scrubbed page view on each navigation. */
export function Analytics() {
  const pathname = usePathname();
  useEffect(() => {
    startAnalytics();
  }, []);
  useEffect(() => {
    track("$pageview", { $current_url: scrubUrl(window.location.href), page: scrubUrl(pathname) });
  }, [pathname]);
  return null;
}
