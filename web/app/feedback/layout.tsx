import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Feedback | Taal",
  description: "Practitioner feedback on Taal: a short form for retail and supply-chain practitioners.",
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
