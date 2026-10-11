"use client";

import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";
import { formatLatency, modelChipText, modelInfoFromHealth, type ModelInfo } from "../lib/health";
import type { HealthResponse } from "../lib/types";
import styles from "./ModelChip.module.css";

// /health is read once per page: the trace header, the Plan live panel and the pass-rate chip can all
// be on screen. A failed read is not kept, so the next mount asks again.
let healthOnce: Promise<HealthResponse | null> | null = null;
export function readHealthOnce(): Promise<HealthResponse | null> {
  if (!healthOnce) {
    healthOnce = getHealth().catch(() => {
      healthOnce = null;
      return null;
    });
  }
  return healthOnce;
}

// The last model id /health named. A later /health that fails, or comes from a cold instance whose
// check names none, must not drop the id from a run that already showed it.
let lastKnown: ModelInfo | null = null;
async function readModelInfo(): Promise<ModelInfo | null> {
  const info = modelInfoFromHealth(await readHealthOnce());
  if (info) lastKnown = info;
  else healthOnce = null; // names no model this time: ask again next time
  return info ?? lastKnown;
}

/** `gemini-3.5-flash · 1.2 s`: the model /health names and how long the run took. The fallback model
 * is in the tooltip only. Renders nothing when health names no model (or, with `plainTimeWithoutModel`,
 * just the run time); the time is left out when the run has no duration yet. It never replaces the provenance badge (Live · Gemini) next to it. */
export function ModelChip({
  latencyMs,
  plainTimeWithoutModel = false,
  runModel = null,
}: {
  latencyMs?: number | null;
  plainTimeWithoutModel?: boolean;
  /** The model id the run itself reports (its run_summary.model), used when /health names none. */
  runModel?: string | null;
}) {
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
  if (!info && runModel && /^gemini-[A-Za-z0-9._-]+$/.test(runModel)) {
    const { text, title } = modelChipText({ model: runModel, fallback: null, live: true }, latencyMs);
    return (
      <span className={`chip ${styles.model}`} title={title} data-testid="model-chip" data-live="true">
        {text}
      </span>
    );
  }
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
