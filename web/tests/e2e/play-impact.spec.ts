import { test, expect } from "@playwright/test";
import { audienceChain, derivePlayNet, playImpact, type ImpactInput } from "../../lib/impact";
import { inr, inrSigned, liftInPoints, pointsFromPp } from "../../lib/format";

// Pure functions behind the canonical figure ("Recovered vs doing nothing"). No browser. The
// numbers are the recorded plays' own (web/mocks/plays.json and coordination/economics_investigation.md).

const chipsStub: ImpactInput = {
  mechanic: "bundle",
  expected_outcome: { margin_inr: 235.14, waste_avoided_inr: 541.8 },
  counterfactuals: { do_nothing_inr: 9200, blanket_markdown_inr: 8188.78, blanket_markdown_pct: 20 },
};

// The live flagship: margin 191.88 + waste avoided 574.48 = 766.36 against doing nothing.
const chipsLive: ImpactInput = {
  mechanic: "bundle",
  expected_outcome: { margin_inr: 191.88, waste_avoided_inr: 574.48 },
  counterfactuals: { do_nothing_inr: 9200, blanket_markdown_inr: 8188.78, blanket_markdown_pct: 20 },
};

const tea: ImpactInput = {
  mechanic: "transfer_plus_nudge",
  expected_outcome: { margin_inr: 7497.87, waste_avoided_inr: 7703.87 },
  counterfactuals: { do_nothing_inr: 35020, blanket_markdown_inr: 32015.18, blanket_markdown_pct: 20 },
};

test.describe("playImpact", () => {
  test("a play within 5% of the lot of a blanket markdown is a near tie, and recovered is waste avoided + margin", () => {
    const i = playImpact(chipsLive, { rupees_at_stake: 9200 });
    expect(i.recovered_inr).toBeCloseTo(766.36, 2);
    expect(i.waste_avoided_inr).toBe(574.48);
    expect(i.margin_inr).toBe(191.88);
    expect(i.do_nothing_inr).toBe(-9200);
    expect(i.blanket_inr).toBeCloseTo(-8188.78, 2);
    expect(i.play_net_inr).toBeCloseTo(-8433.64, 2);
    expect(i.comparison.kind).toBe("near_tie");
    expect(i.comparison.delta_inr).toBeCloseTo(-244.86, 2);
    expect(i.comparison.copy).toBe("Within noise of a blanket 20% markdown, but only this play can be measured against a holdout");
    // the two components add up to the headline
    expect(i.components.reduce((sum, c) => sum + c.inr, 0)).toBeCloseTo(i.recovered_inr, 2);
  });

  test("the stub chips fixture gives about 777 and is also a near tie", () => {
    const i = playImpact(chipsStub);
    expect(Math.round(i.recovered_inr)).toBe(777);
    expect(i.comparison.kind).toBe("near_tie");
  });

  test("a play that keeps clearly more than the markdown says by how much", () => {
    const i = playImpact(tea, { rupees_at_stake: 35020 });
    expect(i.comparison.kind).toBe("beats");
    expect(i.comparison.delta_inr).toBeCloseTo(4493.05, 2);
    expect(i.comparison.copy).toBe("Beats a blanket 20% markdown by ₹4,493");
  });

  test("a play that keeps clearly less says what the markdown retains and why the play still matters", () => {
    const i = playImpact({
      mechanic: "bundle",
      expected_outcome: { margin_inr: 100, waste_avoided_inr: 200 },
      counterfactuals: { do_nothing_inr: 10000, blanket_markdown_inr: 5000, blanket_markdown_pct: 20 },
    });
    expect(i.play_net_inr).toBe(-9700);
    expect(i.comparison.kind).toBe("markdown_retains_more");
    expect(i.comparison.delta_inr).toBe(-4700);
    expect(i.comparison.copy).toBe(
      "A blanket 20% markdown would retain ₹4,700 more on this lot; this play keeps margin and can be measured",
    );
  });

  test("the near-tie band is strictly under 5% of the amount at stake", () => {
    const base = {
      mechanic: "bundle",
      expected_outcome: { margin_inr: 0, waste_avoided_inr: 0 },
    };
    // play net = -10000; blanket net = -(10000 - gap)
    const at = (gap: number) =>
      playImpact({ ...base, counterfactuals: { do_nothing_inr: 10000, blanket_markdown_inr: 10000 - gap, blanket_markdown_pct: 20 } }).comparison.kind;
    expect(at(499)).toBe("near_tie");
    expect(at(500)).toBe("markdown_retains_more");
  });

  test("a transfer's avoided waste is counted once: Tea is about -27.5k, not -19.8k", () => {
    const i = playImpact(tea);
    expect(i.play_net_inr).toBeCloseTo(-27522.13, 2);
    expect(i.play_net_inr).not.toBeCloseTo(-19818.26, 0);
    // what the old bar computed, margin - (do_nothing - waste_avoided), for contrast
    expect(7497.87 - (35020 - 7703.87)).toBeCloseTo(-19818.26, 2);
    // for a transfer the margin IS the recovery; the components are waste avoided less transfer cost
    expect(i.recovered_inr).toBeCloseTo(7497.87, 2);
    expect(i.components.map((c) => c.label)).toEqual(["Waste avoided (at cost)", "Transfer cost"]);
    expect(i.components[1].inr).toBeCloseTo(-206, 2);
  });

  test("derivePlayNet: transfer subtracts the whole loss, every other mechanic only the residual", () => {
    expect(derivePlayNet("transfer_plus_nudge", 100, 300, 1000)).toBe(-900);
    expect(derivePlayNet("bundle", 100, 300, 1000)).toBe(-600);
  });

  test("an API-provided counterfactuals.play_net_inr wins over the local derivation", () => {
    const i = playImpact({ ...tea, counterfactuals: { ...tea.counterfactuals, play_net_inr: -27000 } });
    expect(i.play_net_inr).toBe(-27000);
    expect(i.recovered_inr).toBe(8020);
  });

  test("missing optional fields: no gap, no play_net_inr, no blanket pct, non-finite numbers", () => {
    const i = playImpact({
      mechanic: "bundle",
      expected_outcome: { margin_inr: 50, waste_avoided_inr: Number.NaN },
      counterfactuals: { do_nothing_inr: 1000, blanket_markdown_inr: 900 } as ImpactInput["counterfactuals"],
    });
    expect(Number.isFinite(i.recovered_inr)).toBe(true);
    expect(i.waste_avoided_inr).toBe(0);
    expect(i.comparison.copy).toContain("20%");
    // nothing at stake at all: still a result, never NaN
    const empty = playImpact({
      mechanic: "bundle",
      expected_outcome: { margin_inr: 0, waste_avoided_inr: 0 },
      counterfactuals: { do_nothing_inr: 0, blanket_markdown_inr: 0, blanket_markdown_pct: 20 },
    });
    expect(empty.recovered_inr).toBe(0);
    expect(empty.comparison.kind).toBe("near_tie");
  });

  test("the blanket percentage in the copy follows the play (quinoa's markdown is 10%)", () => {
    const i = playImpact({
      mechanic: "outlet_markdown",
      expected_outcome: { margin_inr: 566.02, waste_avoided_inr: 4136.3 },
      counterfactuals: { do_nothing_inr: 11210, blanket_markdown_inr: 11152.8, blanket_markdown_pct: 10 },
    });
    expect(i.comparison.kind).toBe("beats");
    expect(i.comparison.copy).toMatch(/^Beats a blanket 10% markdown by ₹/);
  });
});

test.describe("audienceChain", () => {
  test("states consented, minus subscribers, equals eligible, then the split", () => {
    expect(audienceChain({ treated_n: 316, holdout_n: 36, eligible_n: 352, excluded_subscribers: 2 })).toBe(
      "354 consented, minus 2 subscribers, equals 352: 316 treated and 36 holdout",
    );
    expect(audienceChain({ treated_n: 10, holdout_n: 1, eligible_n: 11, excluded_subscribers: 1 })).toBe(
      "12 consented, minus 1 subscriber, equals 11: 10 treated and 1 holdout",
    );
  });
  test("no subscribers excluded drops the subtraction; an old payload without eligible_n gives null", () => {
    expect(audienceChain({ treated_n: 316, holdout_n: 36, eligible_n: 352, excluded_subscribers: 0 })).toBe("352 consented: 316 treated and 36 holdout");
    expect(audienceChain({ treated_n: 316, holdout_n: 36, eligible_n: 352 })).toBe("352 consented: 316 treated and 36 holdout");
    expect(audienceChain({ treated_n: 316, holdout_n: 36 })).toBeNull();
  });
});

test.describe("formatting", () => {
  test("rupees use Indian digit grouping", () => {
    expect(inr(35020)).toBe("₹35,020");
    expect(inr(1234567)).toBe("₹12,34,567");
    expect(inrSigned(-8423.4)).toBe("-₹8,423");
    expect(inrSigned(8423)).toBe("₹8,423");
  });

  test("lift reads as percentage points with the interval, from the pp fields or from the fractions", () => {
    const fromFractions = liftInPoints({ lift: 0.022855, ci_low: -0.092676, ci_high: 0.060589 });
    expect(fromFractions).toBe("response-rate difference, +2.3 percentage points (95% CI -9.3 to +6.1 points)");
    expect(liftInPoints({ lift: 0.9, ci_low: 0.9, ci_high: 0.9, lift_pp: 2.286, ci_low_pp: -9.268, ci_high_pp: 6.059 })).toBe(fromFractions);
    expect(liftInPoints({ lift: 0.01 })).toBe("response-rate difference, +1.0 percentage points");
    expect(liftInPoints({ lift: null })).toBeNull();
    expect(liftInPoints({})).toBeNull();
  });

  test("a value that rounds to zero carries no sign", () => {
    expect(pointsFromPp(-0.04)).toBe("0.0");
    expect(pointsFromPp(0.04)).toBe("0.0");
  });
});
