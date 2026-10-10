"use client";

import { useEffect, useState } from "react";
import { getPolicy, rerun } from "../lib/api";
import { toApiError, type ApiError } from "../lib/apiError";
import { Badge } from "./Badge";
import { ErrorCard } from "./ErrorCard";
import type { RerunAccepted } from "../lib/types";

export function PolicyEditor({
  gapId,
  onReplanStart,
  replanning,
  refreshKey = 0,
}: {
  gapId: string;
  /** Hands the 202-accepted run to the Desk, which starts <LiveReplan> for it. */
  onReplanStart: (accepted: RerunAccepted) => void;
  /** True for the whole run (POST /rerun through the stream's "done" frame), driven by the Desk
   * -- not just this component's own brief POST request, which `submitting` below covers. */
  replanning: boolean;
  /** Changes whenever a run starts from anywhere (e.g. the Desk's Plan live): re-reads the current
   * version for the label, which a run may have just created. The editor's own text is left alone. */
  refreshKey?: number;
}) {
  const [text, setText] = useState("");
  const [version, setVersion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    getPolicy()
      .then((doc) => {
        if (cancelled) return;
        setText(doc.text);
        setVersion(doc.policy_version);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(toApiError(e, "/policy"));
      });
    return () => {
      cancelled = true;
    };
  }, [loadAttempt]);

  useEffect(() => {
    // Only the version label is refreshed here; if this read fails the label keeps its last value.
    if (refreshKey > 0) getPolicy().then((doc) => setVersion(doc.policy_version)).catch(() => {});
  }, [refreshKey]);

  async function handleReplan() {
    setSubmitting(true);
    setError(null);
    try {
      // The API assigns the next policy version; re-sending the current one would overwrite the current play.
      const accepted = await rerun({ gap_id: gapId, policy_text: text });
      setVersion(accepted.policy_version);
      onReplanStart(accepted);
    } catch (e) {
      setError(toApiError(e, "/rerun"));
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || replanning;

  if (loadError) {
    return (
      <div className="policy-editor">
        <ErrorCard error={loadError} compact onRetry={() => setLoadAttempt((n) => n + 1)} />
      </div>
    );
  }

  return (
    <div className="policy-editor">
      <div className="policy-editor__header">
        <h4>Policy ({version || "loading"})</h4>
        <Badge kind="replay" detail="versioned" />
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        aria-label="Policy text"
      />
      <button type="button" onClick={handleReplan} disabled={busy}>
        {busy ? "Re-planning…" : "Change policy → re-plan"}
      </button>
      {error ? (
        <ErrorCard
          error={error}
          compact
          onRetry={handleReplan}
          title={error.kind === "conflict" ? "A re-plan is already running" : undefined}
          body={error.kind === "conflict" ? "Wait for it to finish, then try again." : undefined}
        />
      ) : null}
    </div>
  );
}
