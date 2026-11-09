"use client";

import { SessionProvider, useSession } from "next-auth/react";
import { createContext, useContext, useEffect, useRef } from "react";
import { identify, resetIdentity } from "@/lib/analytics";

const AuthEnabled = createContext(false);

/** Is optional Google sign-in set up on this deployment? */
export const useAuthEnabled = () => useContext(AuthEnabled);

/** Wraps the app; sign-in only exists when the server has the Google keys. */
export function AuthProvider({ enabled, children }: { enabled: boolean; children: React.ReactNode }) {
  if (!enabled) return <AuthEnabled.Provider value={false}>{children}</AuthEnabled.Provider>;
  return (
    <AuthEnabled.Provider value={true}>
      <SessionProvider refetchOnWindowFocus={false}>
        <IdentifyUser />
        {children}
      </SessionProvider>
    </AuthEnabled.Provider>
  );
}

/** Ties usage stats to the signed-in person (name and email); back to anonymous on sign-out. */
function IdentifyUser() {
  const { data, status } = useSession();
  const wasSignedIn = useRef(false);
  useEffect(() => {
    const email = data?.user?.email;
    if (status === "authenticated" && email) {
      identify(email, { email, name: data?.user?.name ?? null });
      wasSignedIn.current = true;
    } else if (status === "unauthenticated" && wasSignedIn.current) {
      resetIdentity();
      wasSignedIn.current = false;
    }
  }, [status, data]);
  return null;
}
