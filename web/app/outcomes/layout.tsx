import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Outcomes | Taal",
  description: "What the portfolio projects, what one play projects, and what a week of holdout measurement found.",
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
