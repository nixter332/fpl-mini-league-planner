import type { NextConfig } from "next";

// The browser only ever talks to this app; /api/* is proxied to the FastAPI backend,
// which is the only thing that calls FPL (CLAUDE.md rule 3).
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  experimental: {
    // Plans can take several seconds on a cold cache (rivals' squads are fetched politely).
    proxyTimeout: 120_000,
  },
};

export default config;
