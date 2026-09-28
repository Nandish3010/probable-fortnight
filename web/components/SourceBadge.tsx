// Maps a play or planner run's PlanSource (agents/planner/run.py's PLAN_SOURCES; web/lib/types.ts)
// to the right Badge kind: recorded_gemini -> "recorded" (a committed, validated real-Gemini
// transcript; detail defaults to its recording date), scripted_stub -> "scripted" (the stub
// backend standing in for Gemini), deterministic_rules -> "rules" (the model path did not produce
// a play in time; detail defaults to the fallback reason when known -- never rendered as REPLAY,
// since a rules play was never recorded from anything), live_gemini -> "live-gemini" (a real
// Vertex call, in progress or just finished). A missing or unrecognised source falls back to the
// existing REPLAY badge: unknown provenance, not a specific claim about where the play came from.
import { Badge } from "./Badge";
import { formatDate } from "../lib/format";
import type { PlanSource } from "../lib/types";

export function SourceBadge({
  source,
  detail,
  recordedAt,
  fallbackReason,
  title,
}: {
  source: PlanSource | null | undefined;
  /** Overrides the per-kind default detail below, e.g. "3 iterations · 31.2 s" for live_gemini. */
  detail?: string;
  /** recorded_gemini only: used (formatted with formatDate()) when `detail` is not given. */
  recordedAt?: string | null;
  /** deterministic_rules only: shown verbatim when `detail` is not given. */
  fallbackReason?: string | null;
  title?: string;
}) {
  switch (source) {
    case "recorded_gemini":
      return <Badge kind="recorded" detail={detail ?? (recordedAt ? formatDate(recordedAt) : undefined)} title={title} />;
    case "scripted_stub":
      return <Badge kind="scripted" detail={detail} title={title} />;
    case "deterministic_rules":
      return <Badge kind="rules" detail={detail ?? fallbackReason ?? undefined} title={title} />;
    case "live_gemini":
      return <Badge kind="live-gemini" detail={detail} title={title} />;
    default:
      return <Badge kind="replay" detail={detail} title={title ?? "Unknown provenance"} />;
  }
}
