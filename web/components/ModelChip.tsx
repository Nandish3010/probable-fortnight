"use client";

import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";
import { formatLatency, modelChipText, modelInfoFromHealth, type ModelInfo } from "../lib/health";
import styles from "./ModelChip.module.css";

// /health is read once per page: the trace header and the Plan live panel can both be on screen.
let cached: Promise<ModelInfo | null> | null = null;
function readModelInfo(): Promise<ModelInfo | null> {
  if (!cached) {
    cached = getHealth()
      .then((h) => modelInfoFromHealth(h))
      .catch(() => {
        cached = null; // try again next time; nothing is shown meanwhile
        return null;
      });
  }
  return cached;
}

/** `gemini-3.5-flash · 1.2 s`: the model /health names and how long the run took. The fallback model
 * is in the tooltip only. Renders nothing when health names no model (or, with `plainTimeWithoutModel`,
 * just the run time); the time is left out when the run has no duration yet. It never replaces the provenance badge (Live · Gemini) next to it. */
export function ModelChip({ latencyMs, plainTimeWithoutModel = false }: { latencyMs?: number | null; plainTimeWithoutModel?: boolean }) {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  useEffect(() => {
    let cancelled = false;
    readModelInfo().then((m) => {
      if (!cancelled) setInfo(m);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  if (!info) {
    // Where the run time was shown as plain text before, keep showing it when no model is known.
    const lat = plainTimeWithoutModel ? formatLatency(latencyMs) : null;
    return lat ? <span className="muted"> · {lat}</span> : null;
  }
  const { text, title } = modelChipText(info, latencyMs);
  return (
    <span className={`chip ${styles.model}`} title={title} data-testid="model-chip" data-live={info.live ? "true" : "false"}>
      {text}
    </span>
  );
}
