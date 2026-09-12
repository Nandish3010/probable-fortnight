import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Taal — judge mode",
  description: "Taal: the agent that sells what the forecast says you'll throw away.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="top-nav">
          <span className="top-nav__brand">Taal</span>
          <a href="/">Judge mode</a>
          <a href="/desk">Play Desk</a>
          <a href="/phone">Phone view</a>
          <a href="/chat">Chat</a>
          <a href="/outcomes">Outcomes</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
