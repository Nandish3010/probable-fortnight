"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorCard } from "./ErrorCard";
import { GapCard } from "./GapCard";
import { PlayCard } from "./PlayCard";
import { Skeleton } from "./Skeleton";
import { Badge } from "./Badge";
import { getGaps, getPlays } from "../lib/api";
import { toApiError, type ApiError } from "../lib/apiError";
import { pickFeed, FEED_SIZE, type FeedItem } from "../lib/feed";
import { inr } from "../lib/format";
import { HERO_GAP_ID } from "../lib/hero";
import { label } from "../lib/labels";
import { prefersReducedMotion } from "../lib/motion";
import { recordedGaps, recordedPlays } from "../lib/recorded";
import type { Play } from "../lib/types";
import styles from "./DecisionFeed.module.css";

type FeedState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; items: FeedItem[]; recorded: boolean };

const productOf = (item: FeedItem) => item.gap.evidence.sku_name ?? label("sku", item.gap.sku);

/** Three card-shaped placeholders that keep the feed's height while it loads. */
export function FeedSkeleton() {
  return (
    <div aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className={styles.skeletonCard}>
          <Skeleton width="40%" height={14} />
          <Skeleton width="70%" height={22} />
          <Skeleton width="100%" height={16} />
          <Skeleton width="55%" height={44} />
          <Skeleton width="100%" height={120} />
        </div>
      ))}
    </div>
  );
}

/** The phone landing (under 768px): the hero decision first, then the next two by rupees at stake,
 * each a full decision card (PlayCard, mode "feed") with its own Approve pinned to the bottom of
 * the screen. Approving one shows the result in place and offers "Next decision", which brings the
 * next card into view and puts focus on its Approve.
 *
 * Only gaps that have a plan to decide on follow the hero; a hero gap with no plan degrades to the
 * gap alone. Cards beyond the hero have no recorded Gemini run, so each shows its own source
 * badge (Scripted fixture, Rules (fallback), ...) rather than borrowing the hero's. */
export function DecisionFeed({ now, onHeroPlay }: { now?: Date; onHeroPlay?: (play: Play | null) => void }) {
  const [state, setState] = useState<FeedState>({ status: "loading" });
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set());
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);
  const loadSeq = useRef(0);
  const heroCb = useRef(onHeroPlay);
  heroCb.current = onHeroPlay;

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setState({ status: "loading" });
    try {
      const [gaps, plays] = await Promise.all([getGaps(), getPlays()]);
      if (seq !== loadSeq.current) return;
      const items = pickFeed(gaps, plays, HERO_GAP_ID);
      setState({ status: "ready", items, recorded: false });
      heroCb.current?.(items[0]?.play ?? null);
    } catch (e) {
      if (seq !== loadSeq.current) return;
      setState({ status: "error", error: toApiError(e, "/gaps") });
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      loadSeq.current += 1; // a late answer after unmount writes nothing
    };
  }, [load]);

  async function showRecorded() {
    const [gaps, plays] = await Promise.all([recordedGaps(), recordedPlays()]);
    const items = pickFeed(gaps, plays, HERO_GAP_ID);
    setState({ status: "ready", items, recorded: true });
    heroCb.current?.(items[0]?.play ?? null);
  }

  function goNext(from: number) {
    const target = itemRefs.current[from + 1];
    if (!target) return;
    target.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    const approve = target.querySelector<HTMLButtonElement>('[data-testid="approve-button"]');
    if (approve) approve.focus({ preventScroll: true });
    else target.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
  }

  if (state.status === "loading") {
    return (
      <div className={styles.feed} role="status" aria-busy="true" data-testid="feed-loading">
        <span className="visually-hidden">Loading the top decisions</span>
        <FeedSkeleton />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.feed}>
        <ErrorCard error={state.error} onRetry={load} onShowRecorded={showRecorded} />
      </div>
    );
  }

  const { items, recorded } = state;
  if (items.length === 0) {
    return (
      <div className={styles.feed}>
        <div className={styles.empty} data-testid="feed-empty">
          <h2>No decisions waiting</h2>
          <p>Taal has not found stock at risk today. When it does, plans appear here ranked by rupees at stake.</p>
          {!recorded ? (
            <button type="button" onClick={showRecorded}>
              Show recorded decisions
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <section className={styles.feed} aria-label="Top decisions" data-testid="decision-feed">
      {recorded ? (
        <p className="muted" data-testid="recorded-note">
          <Badge kind="replay" detail="recorded copy" /> The live service is not answering, so these are the recorded
          decisions that ship with the app.
        </p>
      ) : null}
      <ol className={styles.list}>
        {items.map((item, i) => {
          const next = items[i + 1];
          const play = item.play;
          const decided = play ? approvedIds.has(play.play_id) || play.status === "approved" : false;
          return (
            <li
              key={item.gap.gap_id}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              className={styles.item}
              data-testid={`feed-item-${i + 1}`}
            >
              <h2 className={styles.position} tabIndex={-1}>
                Decision {i + 1} of {items.length}
              </h2>
              {play ? (
                <PlayCard
                  play={play}
                  gap={item.gap}
                  mode="feed"
                  now={now}
                  testId={`feed-card-${i + 1}`}
                  liveId={i === 0 ? "approve-live" : `approve-live-${i + 1}`}
                  onApproved={() => setApprovedIds((prev) => new Set(prev).add(play.play_id))}
                />
              ) : (
                <>
                  <GapCard gap={item.gap} now={now} />
                  <p className="muted" data-testid="feed-no-plan">
                    No plan yet for this gap. <Link href="/desk">Open the Play Desk</Link> to plan it live.
                  </p>
                </>
              )}
              {decided ? (
                <div className={styles.next} data-testid="feed-next">
                  {next ? (
                    <>
                      <button type="button" className={styles.nextButton} onClick={() => goNext(i)} aria-describedby={`feed-next-${i}`}>
                        Next decision
                      </button>
                      <p id={`feed-next-${i}`} className={styles.nextText}>
                        {productOf(next)}, {inr(next.gap.rupees_at_stake)} at stake
                      </p>
                    </>
                  ) : (
                    <p className={styles.nextText}>
                      That was the last of the top {items.length}. <Link href="/desk">See every plan in the Play Desk</Link>.
                    </p>
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      {items.length < FEED_SIZE ? (
        <p className="muted">
          Only {items.length} {items.length === 1 ? "decision is" : "decisions are"} waiting.{" "}
          <Link href="/desk">Open the Play Desk</Link> for the rest.
        </p>
      ) : null}
    </section>
  );
}
