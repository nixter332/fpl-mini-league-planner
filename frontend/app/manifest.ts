import type { MetadataRoute } from "next";

// Lets phones "Add to Home Screen" with a proper name and icon, opening without browser bars.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Mini-League Planner",
    short_name: "ML Planner",
    description: "FPL transfer plans built against your mini-league rivals.",
    start_url: "/",
    display: "standalone",
    background_color: "#0b0f14",
    theme_color: "#0b0f14",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
