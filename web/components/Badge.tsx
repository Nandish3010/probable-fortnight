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

// What each badge claims, in one sentence (design_spec.md 8.2). Used as the tooltip on every badge
// and as the text of the landing legend (StateLegend.tsx), so the two cannot drift apart.
export const BADGE_HELP: Record<BadgeKind, string> = {
  live: "This call ran on the service just now.",
  replay: "A recorded run replayed. Nothing was recomputed.",
  "real-pilot": "Measured on a real pilot with real customers.",
  synthetic: "The data is the seeded demo tenant (no real customers, no pilot).",
  recorded: "A real Gemini planner run, recorded earlier and played back.",
  scripted: "A scripted stand-in for the planner model, used when no recording exists.",
  rules: "Taal's rule-based draft, used because the model did not return a plan in time.",
  "live-gemini": "Planned just now by the Gemini model.",
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
    <span className={`badge badge--${kind}`} title={title ?? BADGE_HELP[kind]}>
      <span className="badge__label">{LABELS[kind]}</span>
      {detail ? <span className="badge__detail"> · {detail}</span> : null}
    </span>
  );
}

/** The wording used wherever a call badge sits over the seeded demo tenant's figures (the Approve
 * result, the chat panel, the customer preview): "LIVE · SYNTHETIC data", or "REPLAY · SYNTHETIC
 * data" for a recorded run. A bare LIVE would read as live customer data. The pure-infrastructure
 * health strip does not use it. */
export const SEEDED_DETAIL = "SYNTHETIC data";

export function SeededCallBadge({ live }: { live: boolean }) {
  return (
    <Badge
      kind={live ? "live" : "replay"}
      detail={SEEDED_DETAIL}
      title={`${BADGE_HELP[live ? "live" : "replay"]} ${BADGE_HELP.synthetic}`}
    />
  );
}
