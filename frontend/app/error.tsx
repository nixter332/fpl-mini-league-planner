"use client";

import Link from "next/link";
import { useEffect } from "react";
import { reportError, scrubUrl } from "@/lib/analytics";

// Shown instead of a blank page when a screen crashes.
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    reportError("crash", error.message, { page: scrubUrl(window.location.pathname), digest: error.digest ?? null });
  }, [error]);
  return (
    <main className="flex flex-col items-center gap-3 py-16 text-center">
      <h1 className="m-0 font-display text-xl font-bold">Something broke on this screen</h1>
      <p className="m-0 text-[13px] text-text2">We&apos;ve been told about it. Try again, or start over.</p>
      <div className="flex gap-2">
        <button type="button" onClick={reset} className="h-10 rounded-xl bg-accent px-4 text-[14px] font-semibold text-white">
          Try again
        </button>
        <Link href="/" className="flex h-10 items-center rounded-xl border border-line bg-surface px-4 text-[14px] font-semibold no-underline">
          Start over
        </Link>
      </div>
    </main>
  );
}
