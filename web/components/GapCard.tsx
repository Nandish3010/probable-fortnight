import { Badge } from "./Badge";
import { formatDate, inr, daysUntil } from "../lib/format";
import type { Gap } from "../lib/types";

const DEADLINE_LABEL: Record<string, string> = {
  online_sellby: "Online sell-by",
  expiry: "Expiry",
  lead_time: "Lead time",
};

export const GAP_TYPE_LABEL: Record<string, string> = {
  online_sellby_breach: "Online sell-by breach",
  expiry_writeoff: "Expiry write-off",
  stockout_risk: "Stockout risk",
  rebalance: "Rebalance",
  slow_mover: "Slow mover",
  unmet_demand: "Unmet demand (from chat)",
};

export function GapCard({ gap, now }: { gap: Gap; now?: Date }) {
  // `now` must come from the server's pinned clock (see lib/useServerNow.ts), never the
  // browser's -- the demo tenant's deadlines are frozen relative to TAAL_NOW, and the browser
  // clock drifting past that snapshot silently floors every countdown to 0 forever.
  const days = daysUntil(gap.deadline_date, now);
  const deadlineLabel = DEADLINE_LABEL[gap.deadline_type] ?? gap.deadline_type;
  const { requests_count: requestsCount, distinct_customers: distinctCustomers } = gap.evidence;
  return (
    <div className="card gap-card">
      <div className="card__header">
        <div>
          <h3>{gap.evidence.sku_name ?? gap.sku}</h3>
          <p className="muted">
            {gap.sku} · node {gap.node_id} · {GAP_TYPE_LABEL[gap.type] ?? gap.type}
          </p>
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
      {requestsCount ? (
        <p className="gap-card__demand">
          {requestsCount} real chat request{requestsCount === 1 ? "" : "s"}
          {distinctCustomers ? ` from ${distinctCustomers} customer${distinctCustomers === 1 ? "" : "s"}` : ""} asking
          for this at this store
        </p>
      ) : null}
    </div>
  );
}
