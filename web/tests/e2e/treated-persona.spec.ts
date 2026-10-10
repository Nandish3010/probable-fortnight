import { test, expect } from "@playwright/test";
import { firstName, treatedCustomerFor } from "../../lib/treatedPersona";
import { chatUrlFor } from "../../lib/chatBridge";
import type { DemoCustomer } from "../../lib/types";
import { mockFixture } from "./helpers";

// Which demo customer a play's offer reaches. No browser: pure functions over the same customer list
// and plays the mock API serves (web/mocks/customers_demo.json, plays.json).

const customers = mockFixture("customers_demo") as DemoCustomer[];
const plays = mockFixture("plays") as { play_id: string; target: { node_ids: string[] } }[];
const play = (id: string) => plays.find((p) => p.play_id === id)!;

test.describe("lib/treatedPersona: treatedCustomerFor", () => {
  test("the Tea play (Dark store 4) reaches Ravi, not Meena", () => {
    expect(treatedCustomerFor(play("play_tea_ds04_v1"), customers)?.customer_id).toBe("CUST-RAVI");
  });
  test("the chips play (Dark store 7) reaches Meena", () => {
    expect(treatedCustomerFor(play("play_chips_ds07_v1"), customers)?.customer_id).toBe("CUST-MEENA");
  });
  test("a holdout customer is never the treated one, even at a target store", () => {
    const divya = customers.find((c) => c.role === "holdout")!;
    expect(divya.home_node_id).toBe("DS-07");
    expect(treatedCustomerFor(play("play_chips_ds07_v1"), [divya, ...customers.filter((c) => c !== divya)])?.customer_id).toBe("CUST-MEENA");
    expect(treatedCustomerFor(play("play_chips_ds07_v1"), [divya])).toBeNull();
  });
  test("the customer already selected wins when they qualify, and not when they do not", () => {
    const both: DemoCustomer[] = [
      { ...customers[0], customer_id: "A", home_node_id: "DS-04" },
      { ...customers[1], customer_id: "B", home_node_id: "DS-04" },
    ];
    expect(treatedCustomerFor(play("play_tea_ds04_v1"), both)?.customer_id).toBe("A");
    expect(treatedCustomerFor(play("play_tea_ds04_v1"), both, "B")?.customer_id).toBe("B");
    expect(treatedCustomerFor(play("play_tea_ds04_v1"), customers, "CUST-MEENA")?.customer_id).toBe("CUST-RAVI");
  });
  test("nobody in the audience: the first non-holdout customer; no customers: null", () => {
    expect(treatedCustomerFor(play("play_kaju_ds01_v1"), customers)?.customer_id).toBe("CUST-MEENA");
    expect(treatedCustomerFor(play("play_kaju_ds01_v1"), customers, "CUST-RAVI")?.customer_id).toBe("CUST-RAVI");
    expect(treatedCustomerFor(null, customers)?.customer_id).toBe("CUST-MEENA");
    expect(treatedCustomerFor(play("play_tea_ds04_v1"), [])).toBeNull();
  });
  test("a customer is addressed by first name", () => {
    expect(firstName({ display_name: "Ravi Kumar" })).toBe("Ravi");
    expect(firstName({ display_name: "Meena" })).toBe("Meena");
  });
  test("the /chat link carries the customer, for pages with no chat panel", () => {
    expect(chatUrlFor("prefill", "CUST-RAVI")).toBe("/chat?as=prefill&customer=CUST-RAVI");
    expect(chatUrlFor("prefill")).toBe("/chat?as=prefill");
    expect(chatUrlFor("holdout")).toBe("/chat?as=holdout");
  });
});
