import { test, expect } from "@playwright/test";
import { formatDemoDate, relativeDate } from "../../lib/format";
import { audienceEstimate, mechanicSentence, rupees, whyNow } from "../../lib/playText";
import type { Play } from "../../lib/types";

// Pure functions: no browser. The demo clock is the server's pinned 12 Sep 2026, 09:00 IST.
const NOW = new Date("2026-09-12T03:30:00Z");

test.describe("relativeDate", () => {
  test("today, tomorrow, yesterday", () => {
    expect(relativeDate("2026-09-12", NOW)?.text).toBe("today");
    expect(relativeDate("2026-09-13", NOW)?.text).toBe("tomorrow");
    expect(relativeDate("2026-09-11", NOW)?.text).toBe("yesterday");
  });

  test("in N days / N days ago, with the weekday date for anything within 14 days", () => {
    const r = relativeDate("2026-09-18", NOW)!;
    expect(r.text).toBe("in 6 days");
    expect(r.long).toBe("in 6 days (Fri 18 Sep)");
    expect(r.absolute).toBe("Fri 18 Sep 2026");
    const past = relativeDate("2026-09-09", NOW)!;
    expect(past.text).toBe("3 days ago");
    expect(past.long).toBe("3 days ago (Wed 9 Sep)");
  });

  test("beyond 14 days the weekday goes; beyond 60 days it is a plain date, and the year only when it differs", () => {
    expect(relativeDate("2026-10-06", NOW)!.long).toBe("in 24 days (6 Oct)");
    expect(relativeDate("2026-11-30", NOW)!.long).toBe("30 Nov");
    expect(relativeDate("2027-07-09", NOW)!.long).toBe("9 Jul 2027");
    expect(relativeDate("2027-07-09", NOW)!.absolute).toBe("Fri 9 Jul 2027");
  });

  test("not a date is null; an ISO timestamp is read by its date", () => {
    expect(relativeDate("soon", NOW)).toBeNull();
    expect(relativeDate(null, NOW)).toBeNull();
    expect(relativeDate("2026-09-18T00:00:00Z", NOW)!.text).toBe("in 6 days");
  });

  test("the demo date chip", () => {
    expect(formatDemoDate(NOW)).toBe("12 Sep 2026");
  });
});

test.describe("play text", () => {
  test("whyNow: sell-by, expiry, other; without a clock it is a plain date, never a browser-clock countdown", () => {
    expect(whyNow({ units: 368, deadline_type: "online_sellby", deadline_date: "2026-09-18", at_stake_inr: 9200 }, NOW).text).toBe(
      "368 units pass their online sell-by in 6 days (Fri 18 Sep). ₹9,200 is at stake.",
    );
    expect(whyNow({ units: 59, deadline_type: "expiry", deadline_date: "2027-07-09", at_stake_inr: 11210 }, NOW).text).toBe(
      "59 units reach expiry on 9 Jul 2027. ₹11,210 is at stake.",
    );
    expect(whyNow({ units: 1, deadline_type: "online_sellby", deadline_date: "2026-09-09", at_stake_inr: 100 }, NOW).text).toBe(
      "1 unit passed their online sell-by 3 days ago (Wed 9 Sep). ₹100 is at stake.",
    );
    expect(whyNow({ units: 11, deadline_type: "lead_time", deadline_date: "2026-09-15", at_stake_inr: 2860 }, NOW).text).toContain(
      "lead time deadline is in 3 days (Tue 15 Sep)",
    );
    const noClock = whyNow({ units: 368, deadline_type: "online_sellby", deadline_date: "2026-09-18", at_stake_inr: 9200 });
    expect(noClock.text).toContain("pass their online sell-by on 18 ");
    expect(noClock.text).not.toMatch(/ in \d+ days/);
  });

  test("rupees keeps paise only when there are some", () => {
    expect(rupees(58.5)).toBe("₹58.50");
    expect(rupees(61)).toBe("₹61");
  });

  const base = {
    target: { sku: "SKU-MASALA-CHIPS-200G", node_ids: ["DS-07"], units: 368 },
    audience: { size_after_consent: 315 },
    holdout: { fraction: 0.1 },
  };
  const play = (mechanic: string, mechanic_params: object) => ({ ...base, mechanic, mechanic_params }) as unknown as Play;

  test("mechanicSentence is built from the mechanic's own parameters", () => {
    expect(mechanicSentence(play("bundle", { bundle_sku: "SKU-COCONUT-WATER-1L", bundle_price: 58.5 }), NOW)).toBe(
      "Offer a bundle of Masala Chips 200G with Coconut Water 1L at ₹58.50",
    );
    expect(mechanicSentence(play("transfer_plus_nudge", { transfer_to_node: "OUT-01", transfer_units: 103 }), NOW)).toBe(
      "Move 103 units of Masala Chips 200G from Dark store 7 to Outlet 1, then nudge customers there to buy them",
    );
    expect(mechanicSentence(play("outlet_markdown", { markdown_pct: 10 }), NOW)).toBe("Mark Masala Chips 200G down 10% at Dark store 7");
    expect(mechanicSentence(play("preorder", { preorder_eta_date: "2026-09-22" }), NOW)).toBe(
      "Take pre-orders for Masala Chips 200G; the next stock arrives in 10 days (Tue 22 Sep)",
    );
    // an unknown mechanic degrades to its label, never to a blank
    expect(mechanicSentence(play("brand_new", {}), NOW)).toBe("brand_new: Masala Chips 200G");
  });

  test("audienceEstimate: about N of M, at least one held back, and it follows the fraction", () => {
    expect(audienceEstimate(play("bundle", {}))).toMatchObject({ consented: 315, holdout: 32, treated: 283 });
    expect(audienceEstimate(play("bundle", {}), 0.5)).toMatchObject({ holdout: 158, treated: 157 });
    expect(audienceEstimate({ ...play("bundle", {}), audience: { size_after_consent: 0 } } as unknown as Play).holdout).toBe(0);
  });
});
