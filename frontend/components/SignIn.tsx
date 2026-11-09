"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { useAuthEnabled } from "@/components/AuthProvider";
import { track } from "@/lib/analytics";

/** Optional "Sign in with Google" (hidden when sign-in isn't set up). */
export function SignInCard() {
  if (!useAuthEnabled()) return null;
  return <SignInInner />;
}

function SignInInner() {
  const { data, status } = useSession();
  if (status === "loading") return null;
  if (status === "authenticated") {
    return (
      <div className="flex items-center justify-between gap-2 text-xs text-text3" data-testid="signed-in">
        <span className="truncate">Signed in as {data?.user?.name ?? data?.user?.email}</span>
        <button type="button" onClick={() => signOut()} className="shrink-0 font-semibold text-link">
          Sign out
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface p-3.5" data-testid="sign-in">
      <button
        type="button"
        onClick={() => {
          track("sign_in_started");
          signIn("google");
        }}
        className="flex h-11 items-center justify-center gap-2 rounded-xl border border-line bg-bg text-sm font-semibold text-text"
      >
        <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
          <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
          <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
          <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
        </svg>
        Sign in with Google (optional)
      </button>
      <div className="text-[11.5px] leading-snug text-text3">
        You don&apos;t need to sign in. If you do, we record your name and email to see how the app is used. Nothing is shared, and we never ask for your FPL password.
      </div>
    </div>
  );
}
