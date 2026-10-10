import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Phone view | Taal",
  description: "Priya photographs a pallet on her phone; Taal reads the dates, finds the gap and drafts the play.",
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
