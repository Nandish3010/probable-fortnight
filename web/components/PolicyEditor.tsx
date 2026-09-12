"use client";

import { useEffect, useState } from "react";
import { getPolicy, rerun } from "../lib/api";
import { Badge } from "./Badge";
import type { Play } from "../lib/types";

export function PolicyEditor({ gapId, onReplan }: { gapId: string; onReplan: (play: Play) => void }) {
  const [text, setText] = useState("");
  const [version, setVersion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPolicy().then((doc) => {
      setText(doc.text);
      setVersion(doc.policy_version);
    });
  }, []);

  async function handleReplan() {
    setLoading(true);
    setError(null);
    try {
      const res = await rerun({ gap_id: gapId, policy_text: text, policy_version: version });
      setVersion(res.policy_version);
      onReplan(res.play);
    } catch {
      setError("Re-plan failed. Showing last recorded result would be safer here.");
    } finally {
      setLoading(false);
    }
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
      <button type="button" onClick={handleReplan} disabled={loading}>
        {loading ? "Re-planning…" : "Change policy → re-plan"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
