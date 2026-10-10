"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Badge } from "../components/Badge";
import { ChatPanel } from "../components/ChatPanel";
import { DecisionFeed, FeedSkeleton } from "../components/DecisionFeed";
import { ErrorCard } from "../components/ErrorCard";
import { HealthStrip, TenantLine } from "../components/HealthStrip";
import { Icon } from "../components/icons";
import { PlayCard } from "../components/PlayCard";
import { ResetDialog } from "../components/ResetDialog";
import { StateLegend } from "../components/StateLegend";
import { Tour } from "../components/Tour";
import { getGaps, getPlays, resetDemoData } from "../lib/api";
import { toApiError, type ApiError } from "../lib/apiError";
import { formatDemoDate } from "../lib/format";
import { HERO_GAP_ID } from "../lib/hero";
import { clearProgress } from "../lib/progressStore";
import { recordedGaps, recordedPlays } from "../lib/recorded";
import { clearTourSeen } from "../lib/tour";
import { getVisitorId } from "../lib/visitor";
import { isPhoneNow, useIsPhone } from "../lib/useMediaQuery";
import { useServerNow } from "../lib/useServerNow";
import type { Gap, Play } from "../lib/types";
import styles from "./page.module.css";

const HERO_LINE =
  "Taal finds the stock you will throw away and sells it first: legally, to the right people, with a holdout to prove it.";

interface Beat {
  gap: Gap | null;
  play: Play | null;
}

/** The hero gap and its play; the biggest gap there is when the tenant does not have the hero. */
async function loadBeat(): Promise<Beat> {
  const [gaps, heroPlays] = await Promise.all([getGaps(), getPlays({ gap_id: HERO_GAP_ID })]);
  let chosen = gaps.find((g) => g.gap_id === HERO_GAP_ID) ?? null;
  let plays = heroPlays;
  if (!chosen) {
    chosen = gaps[0] ?? null;
    plays = chosen ? await getPlays({ gap_id: chosen.gap_id }) : [];
  }
  return { gap: chosen, play: plays[0] ?? null };
}

type Prefetch = { promise: Promise<Beat>; state: "pending" | "ok" | "failed" };

function startPrefetch(): Prefetch {
  const entry: Prefetch = { promise: loadBeat(), state: "pending" };
  entry.promise.then(
    () => {
      entry.state = "ok";
    },
    () => {
      entry.state = "failed";
    },
  );
  return entry;
}

export default function LandingPage() {
  const serverNow = useServerNow();
  // Under 768px the landing is a feed of the top decisions (components/DecisionFeed.tsx); from 768px
  // up it is the beat below: one button, then one decision card.
  const phone = useIsPhone();
  const [feedPlay, setFeedPlay] = useState<Play | null>(null);
  // Bumped by Reset so the feed loads afresh.
  const [feedKey, setFeedKey] = useState(0);
  const [beatStarted, setBeatStarted] = useState(false);
  const [gap, setGap] = useState<Gap | null>(null);
  const [play, setPlay] = useState<Play | null>(null);
  // True once a live read has come back, so "nothing to show" is not mistaken for "still loading".
  const [beatLoaded, setBeatLoaded] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetNote, setResetNote] = useState<string | null>(null);
  const [beatError, setBeatError] = useState<ApiError | null>(null);
  const [resetError, setResetError] = useState<ApiError | null>(null);
  // True when the beat is showing the copy that ships with the app because the service did not answer.
  const [usingRecorded, setUsingRecorded] = useState(false);

  // The hero gap and play start loading as soon as the page does, so the click opens the beat at
  // once. A failed prefetch is not shown (nobody asked yet); the click then loads afresh, and that
  // outcome, success or error card, is the one the visitor sees.
  const prefetch = useRef<Prefetch | null>(null);
  useEffect(() => {
    if (isPhoneNow()) return; // the phone feed reads its own data
    if (!prefetch.current) prefetch.current = startPrefetch();
  }, []);

  async function runTheBeat() {
    setBeatStarted(true);
    setBeatError(null);
    setBeatLoaded(false);
    setUsingRecorded(false);
    try {
      const pre = prefetch.current;
      prefetch.current = null; // used once: a Retry or a re-run reads the service afresh
      const beat = pre && pre.state !== "failed" ? await pre.promise : await loadBeat();
      setGap(beat.gap);
      setPlay(beat.play);
      setBeatLoaded(true);
    } catch (e) {
      setBeatError(toApiError(e, "/gaps"));
    }
  }

  async function showRecordedBeat() {
    const [gaps, plays] = await Promise.all([recordedGaps(), recordedPlays(HERO_GAP_ID)]);
    setGap(gaps.find((g) => g.gap_id === HERO_GAP_ID) ?? null);
    setPlay(plays[0] ?? null);
    setBeatError(null);
    setUsingRecorded(true);
  }

  async function handleReset() {
    setResetting(true);
    setResetError(null);
    try {
      const res = await resetDemoData();
      setResetNote(`Reset done for visitor ${res.namespace.slice(0, 8)}…`);
      clearProgress();
      try {
        clearTourSeen(window.localStorage, getVisitorId());
      } catch {
        // storage blocked: nothing to clear
      }
      setFeedKey((k) => k + 1);
      setFeedPlay(null);
      setBeatStarted(false);
      setBeatError(null);
      setBeatLoaded(false);
      setUsingRecorded(false);
      setGap(null);
      setPlay(null);
      prefetch.current = isPhoneNow() ? null : startPrefetch();
      setConfirmReset(false);
    } catch (e) {
      setResetError(toApiError(e, "/reset"));
      setConfirmReset(false);
    } finally {
      setResetting(false);
    }
  }

  const beatReady = beatStarted && !beatError && gap && play;
  // The tour starts once a decision card is on screen: the beat card from 768 px up, the loaded feed below.
  const tourReady = phone ? feedPlay !== null : Boolean(beatReady);

  // The button that started the beat is gone once the card mounts, which would drop keyboard focus
  // on <body>. Put it on the card's title instead (unless the visitor already moved on to another
  // control), so the next Tab reaches the card's own controls and Approve.
  const beatPanelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!beatReady) return;
    const a = document.activeElement;
    if (a && a !== document.body) return;
    beatPanelRef.current?.querySelector<HTMLElement>("[data-card-title]")?.focus({ preventScroll: true });
  }, [beatReady]);

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <section className={`${styles.top} ${beatReady ? styles.topCompact : ""}`}>
        <h1 className={styles.heroLine}>{HERO_LINE}</h1>
        <div className={styles.meta}>
          <p
            className={styles.clock}
            data-testid="demo-clock"
            title="Taal runs on a fixed date so the numbers match the recorded run. Every date and countdown here is relative to it."
          >
            {serverNow ? `Demo date: ${formatDemoDate(serverNow)}.` : "Demo mode."} Nothing you do here persists.
          </p>
          <StateLegend />
          <Tour ready={tourReady} onNeedBeat={beatStarted ? undefined : runTheBeat} />
        </div>
      </section>

      {phone ? (
        <section className={styles.phoneLanding} data-testid="phone-landing">
          <DecisionFeed key={feedKey} now={serverNow} onHeroPlay={setFeedPlay} />
          <ChatPanel play={feedPlay} />
        </section>
      ) : (
        <>
          {/* Before the browser has said which layout it is, a phone sees a placeholder, not the desktop button. */}
          <div className={styles.phoneOnly} aria-hidden="true">
            <FeedSkeleton />
          </div>
          <section className={`hero ${styles.desktopOnly}`}>
            {beatReady ? (
              <div data-testid="beat-panel" ref={beatPanelRef}>
                {usingRecorded ? (
                  <p className="muted" data-testid="recorded-note">
                    <Badge kind="replay" detail="recorded copy" /> The live service is not answering, so this is the
                    recorded result that ships with the app.
                  </p>
                ) : null}
                <PlayCard play={play} gap={gap} mode="hero" now={serverNow} />
              </div>
            ) : (
              <div className="card">
                <h2>Run the 60-second beat</h2>
                <p className="muted">
                  One click opens a real stock gap, its pre-proposed play, and stops at Approve.
                </p>
                {!beatStarted ? (
                  <button type="button" className="hero__cta" onClick={runTheBeat}>
                    Run the 60-second beat
                  </button>
                ) : beatError ? (
                  <ErrorCard error={beatError} onRetry={runTheBeat} onShowRecorded={showRecordedBeat} />
                ) : usingRecorded ? (
                  <p className="muted">No recorded copy of this gap is available.</p>
                ) : beatLoaded ? (
                  <p className="muted">No plan has been proposed for this gap yet.</p>
                ) : (
                  <p className="muted">Loading gap and play…</p>
                )}
              </div>
            )}

            <ChatPanel play={play} />
          </section>
        </>
      )}

      <section className="card-grid">
        <Link className="card-link" href="/desk">
          <div className="card">
            <div className="card__header">
              <h3>
                <span className="card-link__icon">
                  <Icon name="inbox" size={24} />
                </span>
                Play Desk
              </h3>
              <Badge kind="live" detail="live reads" />
            </div>
            <p className="muted">Inbox ranked by rupees at stake, guardrails, trace, policy editor.</p>
          </div>
        </Link>
        <Link className="card-link" href="/phone">
          <div className="card">
            <div className="card__header">
              <h3>
                <span className="card-link__icon">
                  <Icon name="smartphone" size={24} />
                </span>
                Phone view
              </h3>
              <Badge kind="replay" detail="sample pallet photo" />
            </div>
            <p className="muted">Priya&apos;s capture-to-gap flow. Own upload is experimental.</p>
          </div>
        </Link>
        <Link className="card-link" href="/outcomes">
          <div className="card">
            <div className="card__header">
              <h3>
                <span className="card-link__icon">
                  <Icon name="trending-up" size={24} />
                </span>
                Outcomes
              </h3>
              <Badge kind="synthetic" detail="no pilot yet" />
            </div>
            <p className="muted">Treated vs holdout, the CEO number, unmeasured plays.</p>
          </div>
        </Link>
      </section>

      <footer className="footer">
        <div className="footer__links">
          <a href="https://github.com/Nandish3010/probable-fortnight/raw/main/docs/deck.pdf" target="_blank" rel="noreferrer">
            Deck
          </a>
          <a href="https://github.com/Nandish3010/probable-fortnight" target="_blank" rel="noreferrer">
            Repo
          </a>
          <a href="/feedback">Practitioner feedback</a>
        </div>
        <div className="sim-box">
          <strong>What is simulated:</strong> catalogue, sales history, stock and customers are a seeded
          synthetic tenant. <strong>What is real:</strong> forecasts, agents, guardrails, holdout and
          measurement are real code paths.
        </div>
        <TenantLine />
        <HealthStrip />
        {/* Last in the DOM, so last in the tab order: it clears a session, and nobody should land
           on it on the way to the beat. It asks first. */}
        <div className={styles.footerActions}>
          <div className={styles.footerRow}>
            <button type="button" onClick={() => setConfirmReset(true)} disabled={resetting}>
              {resetting ? "Resetting…" : "Reset demo data"}
            </button>
            {resetNote ? <p className={`muted ${styles.resetNote}`}>{resetNote}</p> : null}
          </div>
          {resetError ? <ErrorCard error={resetError} compact onRetry={handleReset} /> : null}
        </div>
      </footer>

      <ResetDialog
        open={confirmReset}
        busy={resetting}
        onCancel={() => setConfirmReset(false)}
        onConfirm={handleReset}
      />
    </main>
  );
}
