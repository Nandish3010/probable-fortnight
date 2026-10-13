"use client";

import { useEffect, useState } from "react";
import { planLiveEvalText } from "../lib/health";
import { readHealthOnce } from "./ModelChip";
import styles from "./ModelChip.module.css";

/** `Live plans: 22/24 passed (11 Oct), p50 26.5 s`: the committed live-plan evaluation, read from
 * /health `plan_live_eval`. Renders nothing while loading, when /health fails, or on a deploy whose
 * /health does not carry the field yet. */
export function PlanEvalChip() {
  const [text, setText] = useState<string | null>(null);
  const [title, setTitle] = useState<string | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    readHealthOnce().then((h) => {
      if (cancelled) return;
      const t = planLiveEvalText(h?.plan_live_eval);
      setText(t);
      if (t && h?.plan_live_eval) {
        const { total, date } = h.plan_live_eval;
        setTitle(`${total} live planner runs${date ? ` on ${date}` : ""}; a run counts as passed when the model authored the play; runs that could not be observed count as not passed.`);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  if (!text) return null;
  return (
    <span className={`chip ${styles.evalchip}`} title={title} data-testid="plan-eval-chip">
      {text}
    </span>
  );
}
