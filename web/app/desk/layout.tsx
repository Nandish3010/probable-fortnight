import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Play Desk | Taal",
  description: "Review the plays Taal drafted for stock at risk, ranked by rupees at stake, and approve one.",
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
