// Plain-language names for the demo tenant's ids. Client-side on purpose (ux_plan.md section 4,
// D6): the backend schemas reject extra fields, and a name is a display concern. label() returns
// the id itself for anything it does not know, so a new tenant, SKU or mechanic degrades to the
// raw id instead of to a blank or a wrong name. The raw id stays reachable in a <Details>.

export type LabelKind = "sku" | "node" | "segment" | "mechanic" | "guardrail" | "gapType" | "deadline";

// Catalogue vocabulary of the synthetic Kutumb Mart tenant (data/generator/catalog.py). A SKU id is
// "SKU-" + the base name upper-cased with dashes + "-" + the pack size, and its name is
// "<base name> <pack size>", so one list of base names names all 300 SKUs. An id that does not
// follow that shape, or whose base name is not in the list, is returned unchanged.
const SKU_BASE_NAMES = [
  "Masala Chips", "Salted Chips", "Banana Chips", "Murukku", "Mixture", "Bhujia", "Khakhra", "Peanut Chikki", "Popcorn", "Nachos",
  "Roasted Makhana", "Mathri", "Namak Para", "Soya Sticks", "Chakli", "Cola Zero", "Cola Lite", "Cola Classic", "Lemon Soda",
  "Mango Nectar", "Orange Juice", "Buttermilk", "Coconut Water", "Jeera Soda", "Iced Tea", "Energy Drink", "Lassi", "Rose Milk",
  "Cold Coffee", "Guava Juice", "Toor Dal", "Moong Dal", "Chana Dal", "Basmati Rice", "Sona Masoori Rice", "Wheat Atta", "Rava",
  "Poha", "Quinoa", "Ragi Flour", "Besan", "Jaggery", "Sugar", "Rock Salt", "Groundnut Oil", "Sunflower Oil", "Mustard Oil", "Ghee",
  "Idli Rice", "Urad Dal", "Kaju Katli", "Mysore Pak", "Soan Papdi", "Gulab Jamun Tin", "Rasgulla Tin", "Besan Ladoo",
  "Motichoor Ladoo", "Dry Fruit Gift Box", "Peda", "Chikki Assorted", "Halwa", "Barfi", "Curd", "Paneer", "Butter", "Cheese Slices",
  "Toned Milk", "Full Cream Milk", "Flavoured Milk", "Cream", "Darjeeling Tea", "Assam Gold Tea", "Nilgiri Tea", "Green Tea",
  "Masala Chai Blend", "Earl Grey", "White Tea", "Wheat Bread", "Milk Bread", "Rusk", "Khari", "Cream Bun", "Multigrain Bread", "Pav",
  "Dish Soap", "Floor Cleaner", "Detergent Powder", "Toilet Cleaner", "Garbage Bags", "Sponge Pack", "Phenyl", "Scrub Pad",
  "Air Freshener", "Laundry Liquid", "Shampoo", "Bath Soap", "Toothpaste", "Hair Oil", "Face Wash", "Body Lotion", "Hand Wash",
  "Deodorant",
] as const;

const SKU_BASE_BY_KEY: ReadonlyMap<string, string> = new Map(
  SKU_BASE_NAMES.map((name) => [name.toUpperCase().replace(/ /g, "-"), name]),
);

function skuName(id: string): string {
  const m = /^SKU-(.+)-(\d+(?:G|ML|KG|L))$/.exec(id);
  if (!m) return id;
  const base = SKU_BASE_BY_KEY.get(m[1]);
  return base ? `${base} ${m[2]}` : id;
}

// 10 dark stores and 6 outlets (data/generator/generate.py). Typed as the exact ids so a typo in
// this table is a compile error; lookups accept any string.
const NODE_IDS = [
  "DS-01", "DS-02", "DS-03", "DS-04", "DS-05", "DS-06", "DS-07", "DS-08", "DS-09", "DS-10",
  "OUT-01", "OUT-02", "OUT-03", "OUT-04", "OUT-05", "OUT-06",
] as const;
type NodeId = (typeof NODE_IDS)[number];

const NODE_NAMES: Record<NodeId, string> = {
  "DS-01": "Dark store 1", "DS-02": "Dark store 2", "DS-03": "Dark store 3", "DS-04": "Dark store 4", "DS-05": "Dark store 5",
  "DS-06": "Dark store 6", "DS-07": "Dark store 7", "DS-08": "Dark store 8", "DS-09": "Dark store 9", "DS-10": "Dark store 10",
  "OUT-01": "Outlet 1", "OUT-02": "Outlet 2", "OUT-03": "Outlet 3", "OUT-04": "Outlet 4", "OUT-05": "Outlet 5", "OUT-06": "Outlet 6",
};

// k-means customer groups, with the names a person gave them for the demo tenant
// (jobs/sense/segments.py HAND_REVIEWED_NAMES; stable because segment ids are ordered by spend).
// A rebuilt tenant can name them differently, which is why an unknown id falls through unchanged.
const SEGMENT_NAMES: Record<string, string> = {
  seg_1: "Festival sweets loyalists",
  seg_2: "Tea connoisseurs",
  seg_3: "Everyday staples shoppers",
  seg_4: "Personal care regulars",
  seg_5: "Household essentials buyers",
  seg_6: "Casual beverage buyers",
  "*": "All customer groups",
};

export const MECHANIC_LABEL: Record<string, string> = {
  bundle: "Bundle with a popular item",
  usual_order_addon: "Add to the customer's usual order",
  substitution: "Offer a substitute",
  preorder: "Pre-order before the stockout",
  subscription_nudge: "Nudge towards a subscription",
  coupon: "Coupon",
  outlet_markdown: "Mark down at the outlet",
  transfer_plus_nudge: "Transfer stock, then nudge customers",
};

export const GUARDRAIL_LABEL: Record<string, string> = {
  margin_floor: "Margin floor",
  frequency_cap: "Contact frequency cap",
  consent_required: "Customer consent",
  sellby_disclosure: "Best-before disclosure",
  subscription_protect: "Subscriber protection",
  no_cannibalise_stockout: "No clash with a stockout",
  holdout_required: "Holdout group kept",
  cite_or_drop: "Every number is cited",
};

/** The one gap-type label map (GapCard, Desk and Outcomes all use this). */
export const GAP_TYPE_LABEL: Record<string, string> = {
  online_sellby_breach: "Online sell-by breach",
  expiry_writeoff: "Expiry write-off",
  stockout_risk: "Stockout risk",
  rebalance: "Rebalance",
  slow_mover: "Slow mover",
  unmet_demand: "Unmet demand (from chat)",
  assortment_gap: "Assortment gap",
};

export const DEADLINE_LABEL: Record<string, string> = {
  online_sellby: "Online sell-by",
  expiry: "Expiry",
  lead_time: "Lead time",
};

function fromTable(table: Record<string, string>, id: string): string {
  return Object.prototype.hasOwnProperty.call(table, id) ? table[id] : id;
}

/** The plain name for an id, or the id itself when it is not known. */
export function label(kind: LabelKind, id: string): string {
  if (typeof id !== "string" || id === "") return id;
  switch (kind) {
    case "sku":
      return skuName(id);
    case "node":
      return fromTable(NODE_NAMES, id);
    case "segment":
      return fromTable(SEGMENT_NAMES, id);
    case "mechanic":
      return fromTable(MECHANIC_LABEL, id);
    case "guardrail":
      return fromTable(GUARDRAIL_LABEL, id);
    case "gapType":
      return fromTable(GAP_TYPE_LABEL, id);
    case "deadline":
      return fromTable(DEADLINE_LABEL, id);
  }
}

/** Comma-joined plain names for a list of ids, e.g. segments or nodes. */
export function labelList(kind: LabelKind, ids: readonly string[]): string {
  return ids.map((id) => label(kind, id)).join(", ");
}
