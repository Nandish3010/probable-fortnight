// LIVE / REPLAY (and REAL PILOT / SYNTHETIC) badge shown on every panel,
// per the checklist requirement "LIVE / REPLAY badges present on every panel".
export type BadgeKind = "live" | "replay" | "real-pilot" | "synthetic";

const LABELS: Record<BadgeKind, string> = {
  live: "LIVE",
  replay: "REPLAY",
  "real-pilot": "REAL PILOT",
  synthetic: "SYNTHETIC",
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
