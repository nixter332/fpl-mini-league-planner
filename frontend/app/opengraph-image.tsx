import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

// The preview card LinkedIn, WhatsApp and others show for a shared link (built once, at build time).
export const alt = "Mini-League Planner: FPL transfer plans built against your mini-league rivals";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const BG = "#0B0F14";
const SURFACE = "#151B23";
const BORDER = "#2A3441";
const TEXT = "#F1F5F9";
const TEXT2 = "#B4BECB";
const ACCENT = "#5B3DF5";
const GOOD = "#4ADE80";

function Logo() {
  return (
    <svg width="64" height="64" viewBox="0 0 28 28">
      <rect x="1" y="1" width="26" height="26" rx="7" fill="#1F7A4D" />
      <line x1="14" y1="1" x2="14" y2="27" stroke="#FFFFFF" strokeWidth="1.5" />
      <circle cx="14" cy="14" r="5" fill="none" stroke="#FFFFFF" strokeWidth="1.5" />
    </svg>
  );
}

/** An illustrative plan card (not a real manager's plan). */
function PlanCard() {
  const row = (out: string, into: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: 14, background: "#1C2430", borderRadius: 14, padding: "14px 18px" }}>
      <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
        <div style={{ color: "#F87171", fontSize: 15, fontWeight: 700 }}>OUT</div>
        <div style={{ color: TEXT, fontSize: 21, fontWeight: 700, lineHeight: 1.2 }}>{out}</div>
      </div>
      <div style={{ color: TEXT2, fontSize: 26 }}>→</div>
      <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
        <div style={{ color: GOOD, fontSize: 15, fontWeight: 700 }}>IN</div>
        <div style={{ color: TEXT, fontSize: 21, fontWeight: 700, lineHeight: 1.2 }}>{into}</div>
      </div>
    </div>
  );
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: 16, width: 420, padding: 26, borderRadius: 24,
        background: SURFACE, border: `3px solid ${ACCENT}`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontFamily: "Space Grotesk", color: TEXT, fontSize: 28, fontWeight: 700 }}>Plan 1</div>
        <div style={{ color: GOOD, fontSize: 18, fontWeight: 700, background: "#12301F", borderRadius: 999, padding: "6px 14px" }}>
          Free transfer
        </div>
      </div>
      {row("Injured defender", "Defender no rival owns")}
      <div style={{ display: "flex", justifyContent: "space-between", color: TEXT2, fontSize: 20 }}>
        <span>Expected points over 4 GWs</span>
        <span style={{ fontFamily: "Space Grotesk", color: TEXT, fontSize: 28, fontWeight: 700 }}>+9.2</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, background: "#221B45", borderRadius: 14, padding: "12px 16px" }}>
        <div style={{ color: "#A594FF", fontSize: 17, fontWeight: 700 }}>Why this plan</div>
        <div style={{ color: TEXT, fontSize: 18, lineHeight: 1.35 }}>A plain-English reason, built only from the solver&apos;s numbers.</div>
      </div>
    </div>
  );
}

export default async function OpengraphImage() {
  // The app's heading font, bold (SIL OFL, see assets/fonts). Body text uses the default font.
  const display = await readFile(join(process.cwd(), "assets/fonts/SpaceGrotesk-Bold.woff"));
  return new ImageResponse(
    (
      <div style={{ display: "flex", width: "100%", height: "100%", background: BG, padding: "64px 72px", gap: 56, alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", flex: 1, gap: 26 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <Logo />
            <div style={{ fontFamily: "Space Grotesk", color: TEXT, fontSize: 36, fontWeight: 700 }}>Mini-League Planner</div>
          </div>
          <div style={{ fontFamily: "Space Grotesk", color: TEXT, fontSize: 68, fontWeight: 700, lineHeight: 1.05, letterSpacing: -1.5 }}>
            Beat your mini‑league, not the template.
          </div>
          <div style={{ color: TEXT2, fontSize: 28, lineHeight: 1.35 }}>
            Free FPL transfer plans built against your rivals&apos; squads, with the numbers behind every move.
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            {["Protect lead", "Balanced", "Risky"].map((s, i) => (
              <div
                key={s}
                style={{
                  display: "flex", fontFamily: "Space Grotesk", fontSize: 22, fontWeight: 700, borderRadius: 12, padding: "10px 18px",
                  color: i === 1 ? "#FFFFFF" : TEXT2, background: i === 1 ? ACCENT : SURFACE, border: `2px solid ${i === 1 ? ACCENT : BORDER}`,
                }}
              >
                {s}
              </div>
            ))}
          </div>
          <div style={{ color: "#94A0AF", fontSize: 21 }}>No login. We never ask for your FPL password.</div>
        </div>
        <PlanCard />
      </div>
    ),
    { ...size, fonts: [{ name: "Space Grotesk", data: display, weight: 700, style: "normal" }] },
  );
}
