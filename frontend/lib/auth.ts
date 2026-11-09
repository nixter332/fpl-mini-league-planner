// Optional Google sign-in (Auth.js / next-auth v4). Server-side only: the secrets are Vercel
// environment variables, never in the code or the browser (CLAUDE.md rule 5).
//   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET  from Google Cloud Console (docs/deploy.md)
//   NEXTAUTH_SECRET                          a random string that signs the login cookie
// Sessions live in that signed cookie (no database). Sign-in only identifies the person for
// usage stats; it has nothing to do with FPL, and we never ask for an FPL password.

import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

export const authEnabled = Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET && process.env.NEXTAUTH_SECRET);

export const authOptions: NextAuthOptions = {
  providers: authEnabled
    ? [GoogleProvider({ clientId: process.env.GOOGLE_CLIENT_ID!, clientSecret: process.env.GOOGLE_CLIENT_SECRET! })]
    : [],
  session: { strategy: "jwt" },
  secret: process.env.NEXTAUTH_SECRET,
};
