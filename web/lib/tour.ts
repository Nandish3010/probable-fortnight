// The guided tour (E5, ux_plan.md section 3). Pure logic only, so the placement rule and the
// once-per-visitor bookkeeping are unit-tested in node (tests/e2e/tour.spec.ts). The component
// that draws it is components/Tour.tsx.

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export type TourStepId = "decision" | "proof" | "approve" | "offer";

export interface TourStep {
  id: TourStepId;
  /** The value of the `data-tour` attribute on the element(s) this step points at. Anchors are
   * attributes added to the markup, never CSS selectors. Several elements may share one value (the
   * figure and the bars are one anchor). */
  anchor: string;
  text: string;
}

export const TOUR_STEPS: readonly TourStep[] = [
  { id: "decision", anchor: "why-now", text: "This is the decision: stock that will be thrown away." },
  { id: "proof", anchor: "proof", text: "This is Taal's plan, with its proof." },
  { id: "approve", anchor: "approve", text: "You approve here. Nothing is sent until you do." },
  { id: "offer", anchor: "step-offer", text: "Then see what the customer gets, and how it is measured." },
];

/** The attribute that marks the Approve button. The tour avoids every element carrying it. */
export const APPROVE_ANCHOR = "approve";

// ---------- once per visitor ----------

export const TOUR_KEY_PREFIX = "taal_tour:";
/** A kill switch that is not tied to a visitor: with it set the tour never opens by itself (the
 * "Take the tour" link still works). The test suites set it so a first-visit popover does not sit
 * on top of every unrelated flow. */
export const TOUR_OFF_KEY = "taal_tour_off";

export function tourKey(visitorId: string): string {
  return `${TOUR_KEY_PREFIX}${visitorId}`;
}

/** The minimal Storage surface used here, so tests can pass a Map-backed fake. */
export interface TourStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function tourSeen(storage: TourStorage | null, visitorId: string): boolean {
  if (!storage) return true; // no storage, no memory of having shown it: do not nag on every load
  try {
    return storage.getItem(tourKey(visitorId)) !== null;
  } catch {
    return true;
  }
}

export function markTourSeen(storage: TourStorage | null, visitorId: string): void {
  if (!storage) return;
  try {
    storage.setItem(tourKey(visitorId), new Date().toISOString());
  } catch {
    // Blocked or full storage: the tour then simply may show again next visit.
  }
}

/** Reset demo data: the visitor is "new" again, so the tour offers itself again. */
export function clearTourSeen(storage: TourStorage | null, visitorId: string): void {
  if (!storage) return;
  try {
    storage.removeItem(tourKey(visitorId));
  } catch {
    // nothing to clear
  }
}

export function tourDisabled(storage: TourStorage | null): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(TOUR_OFF_KEY) === "1";
  } catch {
    return false;
  }
}

/** Opens by itself only for a visitor who has not seen it and has not switched it off. */
export function shouldAutoStart(storage: TourStorage | null, visitorId: string): boolean {
  return !tourDisabled(storage) && !tourSeen(storage, visitorId);
}

// ---------- geometry ----------

export function unionRect(rects: readonly Rect[]): Rect | null {
  if (rects.length === 0) return null;
  let l = Infinity;
  let t = Infinity;
  let r = -Infinity;
  let b = -Infinity;
  for (const x of rects) {
    l = Math.min(l, x.left);
    t = Math.min(t, x.top);
    r = Math.max(r, x.left + x.width);
    b = Math.max(b, x.top + x.height);
  }
  return { left: l, top: t, width: r - l, height: b - t };
}

/** True when the two rectangles share any area once `a` is grown by `pad` on every side. */
export function intersects(a: Rect, b: Rect, pad = 0): boolean {
  return (
    a.left - pad < b.left + b.width &&
    a.left + a.width + pad > b.left &&
    a.top - pad < b.top + b.height &&
    a.top + a.height + pad > b.top
  );
}

export interface PlaceInput {
  /** What the step points at, in viewport coordinates (null: nothing found, centre the card). */
  anchor: Rect | null;
  /** Rectangles the popover must never touch: every Approve button and its decision row. */
  avoid: readonly Rect[];
  size: { w: number; h: number };
  viewport: { w: number; h: number };
  /** The bottom edge of the sticky nav: the popover never goes under it. */
  topInset: number;
  gap?: number;
  margin?: number;
}

export type Side = "below" | "above" | "right" | "left" | "free";

export interface Placement {
  left: number;
  top: number;
  side: Side;
}

/** Where to put the popover. Tries below, above, right and left of the anchor in that order and
 * takes the first spot that fits on screen, clears the anchor and clears every `avoid` rectangle
 * (with a margin); then sweeps the screen for any such spot; then, if the anchor is in the way
 * (the Approve step on a small screen), for a spot that only clears the `avoid` rectangles. The
 * last resort is the spot overlapping them least. The rule is "flip, never cover Approve". */
export function placePopover(input: PlaceInput): Placement {
  const { avoid, size, viewport, topInset } = input;
  // An anchor that is (or sits inside) an Approve rectangle is placed against that whole rectangle, so
  // "above" and "below" clear the decision row around the button and not just the button.
  const anchor = input.anchor ? unionRect([input.anchor, ...avoid.filter((a) => intersects(a, input.anchor as Rect, 0))]) : null;
  const gap = input.gap ?? 12;
  const margin = input.margin ?? 8;
  const AVOID_PAD = 8;

  const minX = margin;
  const maxX = Math.max(minX, viewport.w - margin - size.w);
  const minY = topInset + margin;
  const maxY = Math.max(minY, viewport.h - margin - size.h);
  const clampX = (x: number) => Math.min(maxX, Math.max(minX, x));
  const clampY = (y: number) => Math.min(maxY, Math.max(minY, y));

  const rectAt = (left: number, top: number): Rect => ({ left, top, width: size.w, height: size.h });
  const fits = (left: number, top: number) => left >= minX && left <= maxX && top >= minY && top <= maxY;
  const clearsAvoid = (r: Rect) => !avoid.some((a) => intersects(r, a, AVOID_PAD));
  const clearsAnchor = (r: Rect) => !anchor || !intersects(r, anchor, 0);

  // Nothing to point at (the anchor is not on screen): centred along the bottom, then the sweep below.
  const cx = anchor ? anchor.left + anchor.width / 2 : viewport.w / 2;
  const cy = anchor ? anchor.top + anchor.height / 2 : viewport.h / 2;
  const candidates: Array<{ left: number; top: number; side: Side }> = anchor
    ? [
        { left: clampX(cx - size.w / 2), top: anchor.top + anchor.height + gap, side: "below" },
        { left: clampX(cx - size.w / 2), top: anchor.top - gap - size.h, side: "above" },
        { left: anchor.left + anchor.width + gap, top: clampY(cy - size.h / 2), side: "right" },
        { left: anchor.left - gap - size.w, top: clampY(cy - size.h / 2), side: "left" },
      ]
    : [{ left: clampX(cx - size.w / 2), top: maxY, side: "free" }];

  for (const c of candidates) {
    const r = rectAt(c.left, c.top);
    if (fits(c.left, c.top) && clearsAnchor(r) && clearsAvoid(r)) return c;
  }

  // Sweep: top to bottom, starting beside the anchor and then at either edge.
  const xs = [clampX(cx - size.w / 2), minX, maxX];
  const sweep = (needAnchorClear: boolean): Placement | null => {
    for (let top = minY; top <= maxY; top += 8) {
      for (const left of xs) {
        const r = rectAt(left, top);
        if (clearsAvoid(r) && (!needAnchorClear || clearsAnchor(r))) return { left, top, side: "free" };
      }
    }
    return null;
  };
  const free = sweep(true) ?? sweep(false);
  if (free) return free;

  // Nothing clears Approve (a viewport far too small): the least-overlapping corner.
  let best: Placement = { left: minX, top: minY, side: "free" };
  let bestScore = Infinity;
  for (let top = minY; top <= maxY; top += 8) {
    for (const left of xs) {
      const r = rectAt(left, top);
      const score = avoid.reduce((sum, a) => {
        const w = Math.min(r.left + r.width, a.left + a.width) - Math.max(r.left, a.left);
        const h = Math.min(r.top + r.height, a.top + a.height) - Math.max(r.top, a.top);
        return sum + (w > 0 && h > 0 ? w * h : 0);
      }, 0);
      if (score < bestScore) {
        bestScore = score;
        best = { left, top, side: "free" };
      }
    }
  }
  return best;
}

/** "Step 2 of 4: This is Taal's plan, with its proof." (the live-region announcement) */
export function stepAnnouncement(index: number): string {
  const n = TOUR_STEPS.length;
  return `Step ${index + 1} of ${n}: ${TOUR_STEPS[index].text}`;
}
