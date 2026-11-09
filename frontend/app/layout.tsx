import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { Analytics } from "@/components/Analytics";
import { AuthProvider } from "@/components/AuthProvider";
import { authEnabled } from "@/lib/auth";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-space-grotesk" });

export const metadata: Metadata = {
  title: "Mini-League Planner",
  description: "FPL transfer plans built against your mini-league rivals.",
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
          <div className="mx-auto flex min-h-dvh w-full max-w-[440px] flex-col px-5 pb-6 pt-5">{children}</div>
        </AuthProvider>
      </body>
    </html>
  );
}
