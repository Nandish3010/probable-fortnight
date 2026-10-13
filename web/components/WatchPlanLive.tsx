"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { readHealthOnce } from "./ModelChip";
import { PlanEvalChip } from "./PlanEvalChip";
import styles from "./WatchPlanLive.module.css";

/** Where the Desk's Plan live starts on the flagship gap (app/desk/page.tsx reads `plan=live` once). */
export const WATCH_PLAN_HREF = "/desk?plan=live";

/** The label names the planner that will actually run: "Gemini" only when /health says the service
 * runs the Vertex backend; the scripted stub (local runs, the mock build) says so instead. Nothing
 * is shown until /health has answered, so the wrong word is never on screen first. */
export const WATCH_GEMINI_LABEL = "Watch Gemini plan a play live";
export const WATCH_SCRIPTED_LABEL = "Watch the scripted planner run live";

/** The quiet secondary action beside the landing's one primary button, and the committed pass-rate
 * chip next to it. A plain link in text weight: it only goes to the Desk, where the existing Plan
 * live steps and provenance labels stream. */
export function WatchPlanLive() {
  const [backend, setBackend] = useState<"vertex" | "stub" | null>(null);
  useEffect(() => {
    let cancelled = false;
    readHealthOnce().then((h) => {
      if (cancelled || !h) return;
      setBackend(h.backend === "vertex" ? "vertex" : "stub");
    });
    return () => {
      cancelled = true;
    };
  }, []);
  if (!backend) return null;
  return (
    <div className={styles.group}>
      <Link
        className={styles.link}
        href={WATCH_PLAN_HREF}
        data-testid="watch-plan-live"
        title={
          backend === "vertex"
            ? "Opens the Play Desk on the flagship gap and starts a real Gemini planning run there, with each step and who produced it."
            : "This service runs the scripted planner (no model call): the steps stream the same way, labelled as a scripted fixture."
        }
      >
        {backend === "vertex" ? WATCH_GEMINI_LABEL : WATCH_SCRIPTED_LABEL}
      </Link>
      <PlanEvalChip />
    </div>
  );
}
