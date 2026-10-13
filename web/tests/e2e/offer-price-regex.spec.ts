import { test, expect } from "@playwright/test";
import { BEST_BEFORE, OFFER_PRICE_50 } from "../live/offerCopy";

// Pure regex checks, no browser. The live specs search the chat log with these patterns, and the
// offer wording comes from templated, BigQuery and pre-generated BigQuery copy.

test.describe("OFFER_PRICE_50", () => {
  const matches = [
    "buy with Cola Classic 250ML for ₹50",
    "at ₹50",
    "together for Rs 50.",
    "are Rs 50 when bought together",
    "just Rs 50",
    "Rs. 50",
    "Rs50",
    "INR 50",
  ];
  for (const s of matches) {
    test(`matches: ${s}`, () => expect(s).toMatch(OFFER_PRICE_50));
  }

  const misses = ["₹500", "Rs 500", "₹5", "for ₹5", "Rs 5", "INR 500"];
  for (const s of misses) {
    test(`does not match: ${s}`, () => expect(s).not.toMatch(OFFER_PRICE_50));
  }

  // The variants produced by the pre-generated BigQuery copy.
  const pregenerated = [
    "Masala Chips 200G and Cola Classic 250ML are Rs 50 when bought together.",
    "Masala Chips 200G and Cola Classic 250ML together for Rs 50. Best-before date is 2026-10-15.",
    "Masala Chips 200G and Cola Classic 250ML just Rs 50.",
    "Pair your Masala Chips 200G with a Cola Classic 250ML for just Rs 50. This bundle offer is best before 2026-10-15. Enjoy your snack!",
    "For your weekly shop: get Masala Chips 200G and Cola Classic 250ML together for Rs 50. Best-before date for this offer is 2026-10-15.",
  ];
  for (const s of pregenerated) {
    test(`matches pre-generated copy: ${s.slice(0, 60)}`, () => expect(s).toMatch(OFFER_PRICE_50));
  }
});

test.describe("BEST_BEFORE", () => {
  for (const s of ["Best-before date is 2026-10-15", "best before 2026-10-15", "Best before 2026-10-15", "ಬಳಕೆಗೆ ಮೊದಲು 2026-10-15"]) {
    test(`matches: ${s}`, () => expect(s).toMatch(BEST_BEFORE));
  }
  test("does not match unrelated text", () => expect("Masala Chips 200G for Rs 50").not.toMatch(BEST_BEFORE));
});
