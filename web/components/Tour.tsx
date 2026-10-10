"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import {
  APPROVE_ANCHOR,
  TOUR_STEPS,
  markTourSeen,
  placePopover,
  shouldAutoStart,
  stepAnnouncement,
  unionRect,
  type Placement,
  type Rect,
} from "../lib/tour";
import { getVisitorId } from "../lib/visitor";
import styles from "./Tour.module.css";

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

const toRect = (r: DOMRect): Rect => ({ left: r.left, top: r.top, width: r.width, height: r.height });

/** The visible elements carrying data-tour="<anchor>". */
function anchorElements(anchor: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${anchor}"]`)).filter((el) => el.getClientRects().length > 0);
}

/** Every Approve button on screen and the decision row around it: the popover keeps clear of both. */
function approveRects(): Rect[] {
  const out: Rect[] = [];
  for (const el of anchorElements(APPROVE_ANCHOR)) {
    out.push(toRect(el.getBoundingClientRect()));
    const row = el.closest<HTMLElement>('[data-testid="decision"]');
    if (row) out.push(toRect(row.getBoundingClientRect()));
  }
  return out;
}

interface Layout {
  placement: Placement;
  ring: Rect | null;
}

/** The guided tour (E5): four coach-marks on the landing, once per visitor, dismissible at any
 * moment. Renders the "Take the tour" link (for the legend row) and, while open, a popover placed
 * beside what it points at and never over an Approve button. On a phone it is the same card, kept
 * compact and clear of the sticky Approve bar by the same placement rule.
 *
 * `ready` is true once the decision card is on screen (the beat card on desktop, the loaded feed on
 * a phone). `onNeedBeat` lets the link start the beat when a visitor asks for the tour before it. */
export function Tour({ ready, onNeedBeat }: { ready: boolean; onNeedBeat?: () => void }) {
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [announce, setAnnounce] = useState("");
  const popRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const previous = useRef<HTMLElement | null>(null);
  const wantOpen = useRef(false);
  const autoDone = useRef(false);
  const textId = useId();
  const step = TOUR_STEPS[index];

  const start = useCallback(() => {
    previous.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    markTourSeen(storage(), getVisitorId());
    setIndex(0);
    setLayout(null);
    setAnnounce(stepAnnouncement(0));
    setOpen(true);
  }, []);

  const close = useCallback((restoreFocus = true) => {
    setOpen(false);
    setLayout(null);
    setAnnounce("");
    const back = previous.current;
    previous.current = null;
    if (!restoreFocus) return;
    // Back to where the visitor was; if that element is gone, to the page's main region.
    const target = back && back.isConnected ? back : document.getElementById("main-content");
    target?.focus({ preventScroll: true });
  }, []);

  // Starts by itself once, after the card is on screen, for a visitor who has not seen it. Reset
  // clears the memory and the card goes away and comes back, so this re-arms when `ready` drops.
  useEffect(() => {
    if (!ready) {
      autoDone.current = false;
      return;
    }
    if (wantOpen.current) {
      wantOpen.current = false;
      autoDone.current = true;
      const id = window.setTimeout(start, 250);
      return () => window.clearTimeout(id);
    }
    if (autoDone.current) return;
    autoDone.current = true;
    if (!shouldAutoStart(storage(), getVisitorId())) return;
    const id = window.setTimeout(start, 500);
    return () => window.clearTimeout(id);
  }, [ready, start]);

  function onLink() {
    if (open) return;
    if (ready) start();
    else {
      wantOpen.current = true;
      onNeedBeat?.();
    }
  }

  // Esc closes from anywhere on the page; clicking Approve itself ends the tour (the page is about to
  // change under it) without taking focus away from the result.
  useEffect(() => {
    if (!open) return;
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    }
    function onClick(e: MouseEvent) {
      if ((e.target as HTMLElement | null)?.closest?.(`[data-tour="${APPROVE_ANCHOR}"]`)) close(false);
    }
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("click", onClick, true);
    };
  }, [open, close]);

  // Place the popover for the current step, and again whenever the page scrolls or resizes.
  useLayoutEffect(() => {
    if (!open) return;
    const pop = popRef.current;
    if (!pop) return;
    anchorElements(step.anchor)[0]?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });

    function update() {
      const popEl = popRef.current;
      if (!popEl) return;
      const vw = document.documentElement.clientWidth;
      const vh = window.innerHeight;
      const topInset = Math.max(0, document.querySelector(".top-nav")?.getBoundingClientRect().bottom ?? 0);
      const els = anchorElements(step.anchor);
      const whole = unionRect(els.map((el) => toRect(el.getBoundingClientRect())));
      // Only the part of the anchor that is on screen counts for placement. An anchor inside the sticky
      // nav (the stepper's Offer step) is on screen even though it is above the nav's bottom edge.
      let anchor: Rect | null = null;
      if (whole) {
        const clipTop = els[0]?.closest(".top-nav") ? 0 : topInset;
        const top = Math.max(whole.top, clipTop);
        const bottom = Math.min(whole.top + whole.height, vh);
        anchor = bottom > top ? { left: whole.left, top, width: whole.width, height: bottom - top } : null;
      }
      const placement = placePopover({
        anchor,
        avoid: approveRects(),
        size: { w: popEl.offsetWidth, h: popEl.offsetHeight },
        viewport: { w: vw, h: vh },
        topInset,
      });
      setLayout({ placement, ring: anchor });
    }

    update();
    let raf = 0;
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(update);
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    const settle = window.setTimeout(update, 250); // fonts and late layout
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [open, step]);

  // Focus moves into the popover once it is placed and visible (a hidden element cannot take focus):
  // onto Next, so Enter goes on. It stays inside until the tour closes.
  const focused = useRef(false);
  useEffect(() => {
    if (!open) {
      focused.current = false;
      return;
    }
    if (layout && !focused.current) {
      focused.current = true;
      nextRef.current?.focus({ preventScroll: true });
    }
  }, [open, layout]);

  function go(to: number) {
    setIndex(to);
    setLayout(null);
    setAnnounce(stepAnnouncement(to));
  }

  function onPopKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("button:not(:disabled)"));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    } else if (!items.includes(active as HTMLElement)) {
      e.preventDefault();
      first.focus();
    }
  }

  const last = index === TOUR_STEPS.length - 1;
  const place = layout?.placement;

  return (
    <>
      <button type="button" className={styles.link} onClick={onLink} data-testid="take-tour" aria-haspopup="dialog">
        Take the tour
      </button>
      {/* Present from the first render so the per-step announcements register. */}
      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true" data-testid="tour-live">
        {announce}
      </div>
      {open
        ? createPortal(
            <>
              {layout?.ring ? (
                <div
                  className={styles.ring}
                  aria-hidden="true"
                  data-testid="tour-ring"
                  style={{
                    left: layout.ring.left - 4,
                    top: layout.ring.top - 4,
                    width: layout.ring.width + 8,
                    height: layout.ring.height + 8,
                  }}
                />
              ) : null}
              <div
                ref={popRef}
                className={styles.pop}
                role="dialog"
                aria-label="Guided tour"
                aria-describedby={textId}
                data-testid="tour"
                data-step={step.id}
                data-side={place?.side}
                style={{ left: place?.left ?? 0, top: place?.top ?? 0, visibility: place ? "visible" : "hidden" }}
                onKeyDown={onPopKey}
              >
                <p className={styles.count}>
                  Step {index + 1} of {TOUR_STEPS.length}
                </p>
                <p id={textId} className={styles.text}>
                  {step.text}
                </p>
                <div className={styles.actions}>
                  <button type="button" className={styles.skip} onClick={() => close()} data-testid="tour-skip">
                    Skip tour
                  </button>
                  <span className={styles.spacer} />
                  {index > 0 ? (
                    <button type="button" className={styles.back} onClick={() => go(index - 1)} data-testid="tour-back">
                      Back
                    </button>
                  ) : null}
                  <button
                    ref={nextRef}
                    type="button"
                    className={styles.next}
                    onClick={() => (last ? close() : go(index + 1))}
                    data-testid="tour-next"
                  >
                    {last ? "Done" : "Next"}
                  </button>
                </div>
              </div>
            </>,
            document.body,
          )
        : null}
    </>
  );
}
