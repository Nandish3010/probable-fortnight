import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Noto_Sans_Kannada } from "next/font/google";
import { SandboxBanner } from "../components/SandboxBanner";
import { SiteFooter } from "../components/SiteFooter";
import TopNav from "../components/TopNav";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

// Kannada glyphs: IBM Plex has none, so without this the browser falls back to whatever system
// face it finds (or tofu). Loaded as a subset (only the kannada unicode-range file is fetched
// when a Kannada character is on the page) and placed after Plex in --font-sans (globals.css).
const notoKannada = Noto_Sans_Kannada({
  subsets: ["kannada"],
  weight: ["400", "500", "600"],
  variable: "--font-noto-kannada",
  display: "swap",
  preload: false, // fetched only when a Kannada glyph is on the page; keeps it off the landing critical path
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

// The default title is the landing page's; every other route sets its own in its layout.tsx.
export const metadata: Metadata = {
  title: "Taal: sell what the forecast says you'll throw away",
  description:
    "Taal finds the stock a retailer is about to throw away and sells it first: within FSSAI's online sell-by advisory, to the right customers, with a holdout group to measure the result.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} ${notoKannada.variable}`}>
      <body>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <TopNav />
        <SandboxBanner />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
