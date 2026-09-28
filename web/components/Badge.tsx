// LIVE / REPLAY (and REAL PILOT / SYNTHETIC) badge shown on every panel, per the checklist
// requirement "LIVE / REPLAY badges present on every panel". Also carries the four planner-play
// provenance kinds (PlanSource, web/lib/types.ts) that SourceBadge.tsx (this directory) maps onto:
// "recorded" (a committed, validated real-Gemini recording), "scripted" (the stub backend
// standing in for Gemini), "rules" (the deterministic fallback, never shown as REPLAY -- a rules
// play is not "replaying" anything recorded), and "live-gemini" (a real Vertex call in progress or
// just completed). Keep the original four kinds unchanged.
export type BadgeKind = "live" | "replay" | "real-pilot" | "synthetic" | "recorded" | "scripted" | "rules" | "live-gemini";

const LABELS: Record<BadgeKind, string> = {
  live: "LIVE",
  replay: "REPLAY",
  "real-pilot": "REAL PILOT",
  synthetic: "SYNTHETIC",
  recorded: "Recorded from Gemini",
  scripted: "Scripted fixture",
  rules: "Rules (fallback)",
  "live-gemini": "Live · Gemini",
};

export function Badge({
  kind,
  detail,
  title,
}: {
  kind: BadgeKind;
  detail?: string;
  title?: string;
}) {
  return (
    <span className={`badge badge--${kind}`} title={title}>
      {LABELS[kind]}
      {detail ? <span className="badge__detail"> · {detail}</span> : null}
    </span>
  );
}
