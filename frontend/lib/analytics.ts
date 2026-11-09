// Anonymous usage tracking with PostHog (phase 6). Off unless NEXT_PUBLIC_POSTHOG_KEY is set.
//
// Privacy: no names, no team or league IDs. Page addresses contain team IDs (/team/5179483,
// ?team=...), so every URL-like property is scrubbed before it's sent: long numbers become
// ":id" and query strings are dropped. Nobody is identified; PostHog's random ID is per browser.
// The PostHog project key is meant to be public (it can only send events), so it's fine here.

import posthog, { type CaptureResult } from "posthog-js";

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

let started = false;

/** "/team/5179483?league=1883627" -> "/team/:id" (also for full URLs). */
export function scrubUrl(value: string): string {
  const bare = value.split(/[?#]/)[0];
  const origin = bare.match(/^[a-z]+:\/\/[^/]+/i)?.[0] ?? ""; // keep the site's own address as is
  return origin + bare.slice(origin.length).replace(/\d{3,}/g, ":id");
}

function scrub(event: CaptureResult | null): CaptureResult | null {
  if (!event) return event;
  for (const bag of [event.properties, event.$set, event.$set_once]) {
    if (!bag) continue;
    for (const [k, v] of Object.entries(bag)) {
      if (typeof v === "string" && /url|pathname|referrer|href/i.test(k)) bag[k] = scrubUrl(v);
    }
  }
  return event;
}

export function startAnalytics(): void {
  if (started || !KEY || typeof window === "undefined") return;
  posthog.init(KEY, {
    api_host: HOST,
    autocapture: false, // only the events we choose
    capture_pageview: false, // sent by <Analytics /> with a scrubbed address
    capture_pageleave: false,
    disable_session_recording: true,
    person_profiles: "identified_only", // we never identify anyone
    before_send: scrub,
    disable_compression: true, // small payloads; keeps what we send inspectable
    request_batching: false, // a handful of events per visit: send each as it happens
    advanced_disable_flags: true, // no feature flags, so no flag lookups
    disable_surveys: true,
    disable_external_dependency_loading: true, // never load extra PostHog scripts
    debug: process.env.NEXT_PUBLIC_POSTHOG_DEBUG === "1",
    // Debug builds only: PostHog drops events from headless browsers (bots), which includes the
    // privacy test. Real visitors are never affected.
    opt_out_useragent_filter: process.env.NEXT_PUBLIC_POSTHOG_DEBUG === "1",
  });
  // Tag every event, so this app can share a PostHog project with others and still be filtered.
  posthog.register({ app: "fpl-mini-league-planner" });
  started = true;
}

/** Record an event; does nothing when tracking is off. */
export function track(event: string, props?: Record<string, string | number | boolean | null>): void {
  if (!started) return;
  try {
    posthog.capture(event, props);
  } catch (e) {
    if (process.env.NEXT_PUBLIC_POSTHOG_DEBUG === "1") console.log("[track] failed", String(e));
  }
}
