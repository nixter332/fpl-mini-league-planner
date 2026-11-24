import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { Analytics } from "@/components/Analytics";
import { Suspense } from "react";
import { AppNav, DemoBanner } from "@/components/AppNav";
import { AuthProvider } from "@/components/AuthProvider";
import { authEnabled } from "@/lib/auth";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-space-grotesk" });

// The public address, so link previews get absolute image URLs. Override with NEXT_PUBLIC_SITE_URL.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://fpl-mini-league-planner.vercel.app";
const SHARE_TITLE = "Mini-League Planner: FPL transfer plans to beat your mini-league";
const SHARE_DESCRIPTION =
  "Free FPL transfer plans built against your own mini-league rivals, with the numbers behind every move. No login, never your FPL password.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "Mini-League Planner",
  description: "FPL transfer plans built against your mini-league rivals.",
  appleWebApp: { capable: true, title: "ML Planner", statusBarStyle: "black" },
  // The image comes from app/opengraph-image.tsx (Next adds og:image and its size automatically).
  openGraph: { type: "website", url: "/", siteName: "Mini-League Planner", title: SHARE_TITLE, description: SHARE_DESCRIPTION, locale: "en_GB" },
  twitter: { card: "summary_large_image", title: SHARE_TITLE, description: SHARE_DESCRIPTION },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0B0F14" };

// Applied before paint so the saved theme never flashes. Dark is the default.
const themeScript = `try{var t=localStorage.getItem("theme");if(t==="light")document.documentElement.dataset.theme="light"}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-sans antialiased">
        <Analytics />
        <AuthProvider enabled={authEnabled}>
          <div className="mx-auto flex min-h-dvh w-full max-w-[440px] flex-col px-5 pb-6 pt-5">
            <Suspense fallback={null}>
              <DemoBanner />
            </Suspense>
            {children}
            <Suspense fallback={null}>
              <AppNav />
            </Suspense>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
