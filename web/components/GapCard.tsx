import { Badge } from "./Badge";
import { Details } from "./Details";
import { RelativeDate } from "./RelativeDate";
import { daysUntil, inr } from "../lib/format";
import { DEADLINE_LABEL, GAP_TYPE_LABEL, label } from "../lib/labels";
import type { Gap } from "../lib/types";

/** The gap's facts: units, rupees at stake, days left, the sell-by rule, the pack expiry and any
 * real customer demand. `variant="facts"` is the same content without the card frame and header,
 * for the "Why now" section inside the decision card's Details (components/PlayCard.tsx), so the
 * facts are written once. */
export function GapCard({ gap, now, variant = "card" }: { gap: Gap; now?: Date; variant?: "card" | "facts" }) {
  // `now` must come from the server's pinned clock (see lib/useServerNow.ts), never the
  // browser's -- the demo tenant's deadlines are frozen relative to TAAL_NOW, and the browser
  // clock drifting past that snapshot silently floors every countdown to 0 forever.
  const days = daysUntil(gap.deadline_date, now);
  const deadlineLabel = DEADLINE_LABEL[gap.deadline_type] ?? gap.deadline_type;
  const { requests_count: requestsCount, distinct_customers: distinctCustomers } = gap.evidence;
  const facts = (
    <>
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
      {/* The countdown is the third stat above; this line only explains the rule, and only for a
         gap that has one. It used to repeat the countdown and print the sell-by rule's
         "30% / 45 days" under every gap type, including ones that have no sell-by rule. */}
      {gap.deadline_type === "online_sellby" ? (
        <p className="gap-card__rule">
          Sold within FSSAI&apos;s online sell-by advisory for e-commerce food sellers (Online sell-by rule{" "}
          {gap.evidence.sellby_rule}): stock can be sold online until 30% of its shelf life, or 45 days, whichever is
          fewer days, is left before expiry.
        </p>
      ) : null}
      {gap.evidence.expiry_date ? (
        <p className="gap-card__expiry">
          Pack expiry: <RelativeDate date={gap.evidence.expiry_date} now={now} long />
        </p>
      ) : null}
      {requestsCount ? (
        <p className="gap-card__demand">
          {requestsCount} real chat request{requestsCount === 1 ? "" : "s"}
          {distinctCustomers ? ` from ${distinctCustomers} customer${distinctCustomers === 1 ? "" : "s"}` : ""} asking
          for this at this store
        </p>
      ) : null}
    </>
  );

  if (variant === "facts") return <div className="gap-card gap-card--facts">{facts}</div>;

  return (
    <div className="card gap-card">
      <div className="card__header">
        <div>
          <h3>{gap.evidence.sku_name ?? label("sku", gap.sku)}</h3>
          <p className="muted">
            {label("node", gap.node_id)} · {GAP_TYPE_LABEL[gap.type] ?? gap.type}
          </p>
          <Details inline summary="ids" testId="gap-ids">
            {gap.sku} · {gap.node_id} · {gap.gap_id} · {gap.type}
          </Details>
        </div>
        <Badge kind="replay" detail="Sense run" />
      </div>
      {facts}
    </div>
  );
}
