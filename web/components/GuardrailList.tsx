import { guardrailState, summarizeGuardrails, type GuardrailState } from "../lib/guardrails";
import { label } from "../lib/labels";
import type { Guardrail } from "../lib/types";
import { Details } from "./Details";
import { Icon, type IconName } from "./icons";

// An icon and a word for every state, so no state is colour alone (design_spec.md 4.3).
const ICON: Record<GuardrailState, IconName> = { pass: "check", not_applicable: "minus", pending: "clock", fail: "x" };
const WORD: Record<GuardrailState, string> = {
  pass: "passed",
  not_applicable: "not applicable",
  pending: "pending",
  fail: "failed",
};
const CLASS: Record<GuardrailState, string> = {
  pass: "guardrails__item--pass",
  not_applicable: "guardrails__item--na",
  pending: "guardrails__item--pending",
  fail: "guardrails__item--fail",
};

/** One line that says what the checks amounted to ("8 checks: 5 passed, 3 not applicable"), with
 * the per-rule list one click away. A rule that passed because there was nothing to check is
 * shown as "not applicable", not as a tick (lib/guardrails.ts). */
export function GuardrailList({ guardrails }: { guardrails: Guardrail[] }) {
  const summary = summarizeGuardrails(guardrails);
  return (
    <details
      className={`guardrails-disclosure${summary.fail > 0 ? " guardrails-disclosure--fail" : ""}`}
      data-testid="guardrails-disclosure"
      open={summary.fail > 0}
    >
      <summary data-testid="guardrail-summary">
        <Icon name={summary.fail > 0 ? "alert-triangle" : "shield-check"} size={16} className="guardrails-disclosure__icon" />
        {summary.text}
      </summary>
      <ul className="guardrails">
        {guardrails.map((g) => {
          const state = guardrailState(g);
          return (
            <li key={g.rule} className={`guardrails__item ${CLASS[state]}`} data-state={state}>
              <span className="guardrails__status"><Icon name={ICON[state]} size={16} /></span>
              <span className="guardrails__rule">
                {label("guardrail", g.rule)}
                <span className="visually-hidden"> ({WORD[state]})</span>
              </span>
              <span className="guardrails__detail">{g.detail}</span>
              <Details inline summary="rule id" testId={`guardrail-id-${g.rule}`}>
                <code className="guardrails__code">{g.rule}</code>
              </Details>
            </li>
          );
        })}
      </ul>
    </details>
  );
}
