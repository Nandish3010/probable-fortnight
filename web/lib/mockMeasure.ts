// Mock-mode stand-in for what the real sandbox does when a visitor's customer orders and Measure
// runs: a measured SYNTHETIC row for each approved play that has at least one mocked order. Only
// used by lib/api.ts in mock mode, so a fast-forward (components/FastForwardPanel.tsx) can be driven
// end to end without a backend. The numbers are computed from the play and the mocked order count,
// never typed, and the row says what it is: data_label SYNTHETIC, inconclusive when the interval
// crosses zero.
import { mockApproveFor, mockJson } from "./mockData";
import type { Outcome, Play } from "./types";

const ORDERS_KEY = "taal_mock_orders";
const MEASURED_KEY = "taal_mock_measured";

interface MockOrder {
  sku: string;
  customer_id: string;
}

function read<T>(key: string): T[] {
  try {
    const raw = typeof window === "undefined" ? null : window.localStorage.getItem(key);
    const v = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(v) ? (v as T[]) : [];
  } catch {
    return [];
  }
}

function write(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked: the mock then simply measures nothing.
  }
}

/** The chat order flow ("add:<sku>") in mock mode: remember who ordered what. */
export function rememberMockOrder(sessionId: string, text: string) {
  const m = /^add:(.+)$/i.exec(text.trim());
  if (!m) return;
  write(ORDERS_KEY, [...read<MockOrder>(ORDERS_KEY), { sku: m[1].trim().toUpperCase(), customer_id: sessionId.split(":")[0] }]);
}

export function mockMeasuredRows(): Outcome[] {
  return read<Outcome>(MEASURED_KEY);
}

export function clearMockMeasure() {
  try {
    window.localStorage.removeItem(ORDERS_KEY);
    window.localStorage.removeItem(MEASURED_KEY);
  } catch {
    // nothing stored
  }
}

/** 95% interval for p1 - p0 by Newcombe's hybrid score method (Wilson interval for each rate). */
export function newcombeInterval(x1: number, n1: number, x0: number, n0: number): { low: number; high: number } {
  const z = 1.96;
  const wilson = (x: number, n: number) => {
    const p = x / n;
    const d = 1 + (z * z) / n;
    const centre = p + (z * z) / (2 * n);
    const half = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
    return { low: (centre - half) / d, high: (centre + half) / d };
  };
  const p1 = x1 / n1;
  const p0 = x0 / n0;
  const w1 = wilson(x1, n1);
  const w0 = wilson(x0, n0);
  return {
    low: p1 - p0 - Math.sqrt((p1 - w1.low) ** 2 + (w0.high - p0) ** 2),
    high: p1 - p0 + Math.sqrt((w1.high - p1) ** 2 + (p0 - w0.low) ** 2),
  };
}

/** Mock Measure: adds a measured row for every approved play whose product was ordered. */
export async function mockMeasure(approvedPlayIds: readonly string[], existing: readonly Outcome[]): Promise<Outcome[]> {
  const orders = read<MockOrder>(ORDERS_KEY);
  const plays = (await mockJson("plays")) as unknown as Play[];
  const rows = mockMeasuredRows();
  for (const id of approvedPlayIds) {
    if (existing.some((o) => o.play_id === id) || rows.some((o) => o.play_id === id)) continue;
    const play = plays.find((p) => p.play_id === id);
    if (!play) continue;
    const ordered = orders.filter((o) => o.sku === play.target.sku.toUpperCase()).length;
    if (ordered === 0) continue;
    const { assignment } = await mockApproveFor(id);
    const n1 = assignment.treated_n;
    const n0 = assignment.holdout_n;
    const ci = newcombeInterval(ordered, n1, 0, n0);
    const lift = ordered / n1;
    const e = play.expected_outcome;
    const share = e.units > 0 ? ordered / e.units : 0;
    const discount = e.discount_cost_inr * share;
    rows.push({
      play_id: id,
      sku: play.target.sku,
      node_id: play.target.node_ids[0],
      mechanic: play.mechanic,
      status: "measured",
      measured_at: new Date().toISOString(),
      min_treated_n: 20,
      treated: {
        customers: n1,
        responders: ordered,
        units: ordered,
        revenue_inr: Math.round(e.margin_inr * share * 100) / 100,
        margin_inr: Math.round(e.margin_inr * share * 100) / 100,
        discount_cost_inr: Math.round(discount * 100) / 100,
      },
      holdout: { customers: n0, responders: 0, units: 0, revenue_inr: 0, margin_inr: 0, discount_cost_inr: 0 },
      lift,
      ci_low: ci.low,
      ci_high: ci.high,
      lift_unit: "percentage_points",
      lift_pp: lift * 100,
      ci_low_pp: ci.low * 100,
      ci_high_pp: ci.high * 100,
      inconclusive: ci.low < 0 && ci.high > 0,
      waste_avoided_inr: Math.round(e.waste_avoided_inr * share * 100) / 100,
      margin_per_discount_rupee: discount > 0 ? Math.round(((e.margin_inr * share) / discount) * 100) / 100 : null,
      waste_kg_est: null,
      co2e_kg_est: null,
      data_label: "SYNTHETIC",
    });
  }
  write(MEASURED_KEY, rows);
  return rows;
}
