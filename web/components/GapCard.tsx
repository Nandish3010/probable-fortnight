import { Badge } from "./Badge";
import { formatDate, inr, daysUntil } from "../lib/format";
import type { Gap } from "../lib/types";

const DEADLINE_LABEL: Record<string, string> = {
  online_sellby: "Online sell-by",
  expiry: "Expiry",
  lead_time: "Lead time",
};

export function GapCard({ gap }: { gap: Gap }) {
  const days = daysUntil(gap.deadline_date);
  const deadlineLabel = DEADLINE_LABEL[gap.deadline_type] ?? gap.deadline_type;
  return (
    <div className="card gap-card">
      <div className="card__header">
        <div>
          <h3>{gap.evidence.sku_name ?? gap.sku}</h3>
          <p className="muted">{gap.sku} · node {gap.node_id}</p>
        </div>
        <Badge kind="replay" detail="Sense run" />
      </div>
      <div className="gap-card__stats">
        <div className="stat">
          <span className="stat__value">{gap.units_at_risk}</span>
          <span className="stat__label">units</span>
        </div>
        <div className="stat">
          <span className="stat__value">{inr(gap.rupees_at_stake)}</span>
          <span className="stat__label">at stake</span>
        </div>
        <div className="stat">
          <span className="stat__value">{Math.max(days, 0)}d</span>
          <span className="stat__label">{deadlineLabel.toLowerCase()}</span>
        </div>
      </div>
      <p className="gap-card__rule">
        {deadlineLabel}: {Math.max(days, 0)} days (rule {gap.evidence.sellby_rule}: 30% / 45 days)
      </p>
      {gap.evidence.expiry_date ? (
        <p className="gap-card__expiry">Pack expiry: {formatDate(gap.evidence.expiry_date)}</p>
      ) : null}
    </div>
  );
}
