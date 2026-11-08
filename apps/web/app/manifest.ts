import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FINN: your portfolio's filings, ranked",
    short_name: "FINN",
    description: "Every NSE filing across your portfolio, ranked by how much it could matter.",
    start_url: "/",
    display: "standalone",
    background_color: "#f4f5f9",
    theme_color: "#4a36b0",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
