import type { Metadata } from "next";
import localFont from "next/font/local";
import { SandboxBanner } from "../components/SandboxBanner";
import { SiteFooter } from "../components/SiteFooter";
import TopNav from "../components/TopNav";
import "./globals.css";

// Self-hosted (web/app/fonts, see the README there): the build must not fetch from Google.
// The Plex Sans and Noto Sans Kannada files are variable fonts, so one file covers 400-600.
const plexSans = localFont({
  src: [
    {
      path: "./fonts/IBMPlexSans-Variable-latin.woff2",
      weight: "400 600",
      style: "normal",
    },
  ],
  variable: "--font-plex-sans",
  display: "swap",
  adjustFontFallback: "Arial",
});

// Kannada glyphs: IBM Plex has none, so without this the browser falls back to whatever system
// face it finds (or tofu). The file is the kannada subset only, restricted by unicode-range so it
// is fetched only when a Kannada character is on the page, and placed after Plex in --font-sans
// (globals.css).
const notoKannada = localFont({
  src: [
    {
      path: "./fonts/NotoSansKannada-Variable-kannada.woff2",
      weight: "400 600",
      style: "normal",
    },
  ],
  variable: "--font-noto-kannada",
  display: "swap",
  preload: false, // fetched only when a Kannada glyph is on the page; keeps it off the landing critical path
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0951-0952, U+0964-0965, U+0B83, U+0C80-0CF3, U+1CD0, U+1CD2-1CD3, U+1CDA, U+1CF2, U+1CF4, U+200C-200D, U+20B9, U+25CC, U+A830-A835",
    },
  ],
});

const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-Regular-latin.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexMono-Medium-latin.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
  adjustFontFallback: "Arial",
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
