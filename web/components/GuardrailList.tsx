import type { Guardrail } from "../lib/types";

export function GuardrailList({ guardrails }: { guardrails: Guardrail[] }) {
  return (
    <ul className="guardrails">
      {guardrails.map((g) => (
        <li key={g.rule} className={`guardrails__item ${g.passed ? "guardrails__item--pass" : "guardrails__item--fail"}`}>
          <span className="guardrails__status" aria-hidden>{g.passed ? "✓" : "✗"}</span>
          <span className="guardrails__rule">{g.rule.replace(/_/g, " ")}</span>
          <span className="guardrails__detail">{g.detail}</span>
        </li>
      ))}
    </ul>
  );
}
