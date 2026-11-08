import type { Metadata, Viewport } from "next";
import { Anek_Latin, Mukta } from "next/font/google";
import RegisterServiceWorker from "@/components/RegisterServiceWorker";
import Tabs from "@/components/Tabs";
import "./globals.css";

const display = Anek_Latin({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-display",
  display: "swap",
});

const text = Mukta({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-text",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "FINN", template: "%s | FINN" },
  description:
    "Every NSE filing across your portfolio, ranked: what to read first, what to skim, what is routine.",
  applicationName: "FINN",
  appleWebApp: { capable: true, title: "FINN", statusBarStyle: "default" },
  icons: {
    icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f5f9" },
    { media: "(prefers-color-scheme: dark)", color: "#16142a" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN" className={`${display.variable} ${text.variable}`}>
      <body>
        {children}
        <Tabs />
        <RegisterServiceWorker />
      </body>
    </html>
  );
}
