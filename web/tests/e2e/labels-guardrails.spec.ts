import { test, expect } from "@playwright/test";
import { GUARDRAIL_LABEL, label, labelList } from "../../lib/labels";
import { guardrailState, summarizeGuardrails } from "../../lib/guardrails";

test.describe("label()", () => {
  test("names the demo tenant's ids", () => {
    expect(label("sku", "SKU-MASALA-CHIPS-200G")).toBe("Masala Chips 200G");
    expect(label("sku", "SKU-WHEAT-ATTA-1KG")).toBe("Wheat Atta 1KG");
    expect(label("sku", "SKU-DARJEELING-TEA-100G")).toBe("Darjeeling Tea 100G");
    expect(label("node", "DS-07")).toBe("Dark store 7");
    expect(label("node", "OUT-02")).toBe("Outlet 2");
    expect(label("mechanic", "transfer_plus_nudge")).toBe("Transfer stock, then nudge customers");
    expect(label("segment", "seg_2")).toBe("Tea connoisseurs");
    expect(label("gapType", "online_sellby_breach")).toBe("Online sell-by breach");
    expect(label("guardrail", "margin_floor")).toBe("Margin floor");
    expect(label("deadline", "online_sellby")).toBe("Online sell-by");
  });

  test("falls back to the id itself for anything it does not know", () => {
    expect(label("sku", "SKU-UNKNOWN-THING-9G")).toBe("SKU-UNKNOWN-THING-9G"); // right shape, unknown base
    expect(label("sku", "SKU-MASALA-CHIPS")).toBe("SKU-MASALA-CHIPS"); // no pack size
    expect(label("sku", "not-a-sku")).toBe("not-a-sku");
    expect(label("node", "DS-99")).toBe("DS-99");
    expect(label("mechanic", "brand_new_mechanic")).toBe("brand_new_mechanic");
    expect(label("segment", "seg_42")).toBe("seg_42");
    expect(label("guardrail", "toString")).toBe("toString"); // object prototype names are not labels
    expect(label("node", "")).toBe("");
  });

  test("every guardrail rule the schema allows has a plain name", () => {
    for (const rule of ["margin_floor", "frequency_cap", "consent_required", "sellby_disclosure", "subscription_protect", "no_cannibalise_stockout", "holdout_required", "cite_or_drop"]) {
      expect(GUARDRAIL_LABEL[rule], rule).toBeTruthy();
      expect(GUARDRAIL_LABEL[rule]).not.toMatch(/_/);
    }
  });

  test("labelList joins names and keeps unknown ids", () => {
    expect(labelList("node", ["DS-04", "DS-99"])).toBe("Dark store 4, DS-99");
  });
});

test.describe("guardrail tri-state", () => {
  const g = (detail: string, passed = true) => ({ passed, detail });

  test("each detail pattern the recorded plays use maps to its state", () => {
    expect(guardrailState(g("net margin 17.79% (net price 61.00, cost 50.15) vs snacks floor 8.00%"))).toBe("pass");
    expect(guardrailState(g("all 313 customers under 2 plays in 7 days"))).toBe("pass");
    expect(guardrailState(g("audience filtered by consent: 379 -> 315"))).toBe("pass");
    expect(guardrailState(g("holdout 10%, min_treated_n 20"))).toBe("pass");
    expect(guardrailState(g("13 number(s) in rationale all cited; 5 citation(s) resolve"))).toBe("pass");

    expect(guardrailState(g("copy pending; best-before disclosure enforced at copy validation"))).toBe("pending");

    expect(guardrailState(g("not a near-deadline play; disclosure not required"))).toBe("not_applicable");
    expect(guardrailState(g("outlet channel: no personal message, consent not required"))).toBe("not_applicable");
    expect(guardrailState(g("preorder does not push SKU-COLA-ZERO-500ML; stockout rule not applicable"))).toBe("not_applicable");
    expect(guardrailState(g("no stockout gap for SKU-MASALA-CHIPS-200G at DS-07"))).toBe("not_applicable");
    expect(guardrailState(g("no active subscribers of SKU-MASALA-CHIPS-200G in audience"))).toBe("not_applicable");
    expect(guardrailState(g("preorder is not a discount play"))).toBe("not_applicable");
    expect(guardrailState(g("all 0 customers under 2 plays in 7 days"))).toBe("not_applicable");
  });

  test("a rule that did not pass is a failure whatever its text says; all 10 customers is not 'all 0'", () => {
    expect(guardrailState(g("no active subscribers of X in audience", false))).toBe("fail");
    expect(guardrailState(g("all 10 customers under 2 plays in 7 days"))).toBe("pass");
  });

  test("summary: '8 checks: 5 passed, 3 not applicable'", () => {
    const eight = [
      g("net margin 17.79% vs snacks floor 8.00%"),
      g("all 0 customers under 2 plays in 7 days"),
      g("outlet channel: no personal message, consent not required"),
      g("not a near-deadline play; disclosure not required"),
      g("holdout 10%, min_treated_n 20"),
      g("13 number(s) in rationale all cited"),
      g("audience filtered by consent: 379 -> 315"),
      g("all 313 customers under 2 plays in 7 days"),
    ];
    const s = summarizeGuardrails(eight);
    expect(s.text).toBe("8 checks: 5 passed, 3 not applicable");
    expect(s).toMatchObject({ total: 8, pass: 5, not_applicable: 3, pending: 0, fail: 0 });
  });

  test("pending and failed are listed only when present; a single check is singular", () => {
    expect(summarizeGuardrails([g("copy pending; x"), g("holdout 10%"), g("bad", false)]).text).toBe("3 checks: 1 passed, 1 pending, 1 failed");
    expect(summarizeGuardrails([g("holdout 10%")]).text).toBe("1 check: 1 passed");
    expect(summarizeGuardrails([]).text).toBe("0 checks: 0 passed");
  });
});
