"use client";

import { useEffect, useState } from "react";
import { getPolicy, rerun } from "../lib/api";
import { Badge } from "./Badge";
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPolicy().then((doc) => {
      setText(doc.text);
      setVersion(doc.policy_version);
    });
  }, []);

  useEffect(() => {
    if (refreshKey > 0) getPolicy().then((doc) => setVersion(doc.policy_version));
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
      setError(e instanceof Error ? e.message : "Re-plan failed. Showing last recorded result would be safer here.");
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || replanning;

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
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
