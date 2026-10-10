"use client";

import { useEffect, useState } from "react";
import { isMockMode } from "../lib/api";
import { containsKannada, langAttr, uniqueByLabel, type ReplyLanguage } from "../lib/lang";
import type { ChatEnvelope } from "../lib/types";
import { Badge } from "./Badge";
import styles from "./MeenaPreview.module.css";

export type PreviewState =
  | { status: "idle" | "loading" }
  | { status: "failed" }
  | {
      status: "ready";
      envelope: ChatEnvelope;
      language: ReplyLanguage;
      /** The reply does not carry this play, so the customer may not be in its audience. */
      offAudience: boolean;
    };

const HIDE_KEY = "taal_hide_gloss";

/** The first real /chat reply for the demo customer, in a phone frame (design_spec.md 6.4). Real
 * text only: while waiting it says the message is being written, on failure it says the preview is
 * unavailable. It never shows placeholder text as if it were the customer's message. */
export function MeenaPreview({
  state,
  name,
  animate,
  onRetry,
}: {
  state: PreviewState;
  name: string;
  /** Slide in over 350 ms (false under reduced motion and for a recorded result). */
  animate: boolean;
  onRetry: () => void;
}) {
  // The English gloss is shown by default; the choice to hide it is remembered per browser.
  const [hideGloss, setHideGloss] = useState(false);
  useEffect(() => {
    try {
      setHideGloss(window.localStorage.getItem(HIDE_KEY) === "1");
    } catch {
      // Storage blocked: the gloss simply stays shown.
    }
  }, []);
  function toggleGloss() {
    const next = !hideGloss;
    setHideGloss(next);
    try {
      window.localStorage.setItem(HIDE_KEY, next ? "1" : "0");
    } catch {
      // Not remembered; still applies for this view.
    }
  }

  const ready = state.status === "ready" ? state : null;
  const gloss = ready?.envelope.english_gloss;

  return (
    <div className={styles.frame} data-testid="meena-preview" data-status={state.status} data-motion={animate ? "on" : "off"}>
      <div className={styles.notch} aria-hidden="true" />
      <div className={styles.head}>
        <p className={styles.title}>What {name} receives</p>
        <Badge kind={isMockMode() ? "replay" : "live"} />
      </div>

      {ready ? (
        <div className={styles.screen}>
          <div className={styles.bubble} data-testid="meena-bubble">
            {ready.language === "english_fallback" ? (
              <span className={styles.tag} data-testid="english-fallback-label">
                English fallback
              </span>
            ) : null}
            <p className={styles.text} lang={langAttr(ready.language)} data-testid="meena-text">
              {ready.envelope.text}
            </p>
            {gloss && !hideGloss ? (
              <>
                <hr className={styles.rule} />
                <p className={styles.gloss} lang="en" data-testid="meena-gloss">
                  {gloss}
                </p>
              </>
            ) : null}
          </div>
          {ready.envelope.buttons && ready.envelope.buttons.length > 0 ? (
            <div className={styles.chips} aria-hidden="true">
              {uniqueByLabel(ready.envelope.buttons).map((b) => (
                <span key={b.id} className={styles.chip} lang={containsKannada(b.label) ? "kn" : undefined}>
                  {b.label}
                </span>
              ))}
            </div>
          ) : null}
          {gloss ? (
            <button type="button" className={styles.toggle} onClick={toggleGloss} aria-pressed={hideGloss} data-testid="meena-gloss-toggle">
              {hideGloss ? "Show English" : "Hide English"}
            </button>
          ) : null}
          {ready.offAudience ? (
            <p className={styles.caption} data-testid="meena-audience-note">
              {name} may not be in this play&apos;s audience.
            </p>
          ) : null}
        </div>
      ) : state.status === "failed" ? (
        <div className={styles.screen}>
          <p className={styles.failed} data-testid="meena-unavailable">
            Preview unavailable. The chat agent did not answer in time.
          </p>
          <button type="button" className={styles.retry} onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : (
        <div className={styles.screen} data-testid="meena-loading">
          <div className={styles.skeleton} aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <p className={styles.waiting}>{name}&apos;s message is being written…</p>
        </div>
      )}
    </div>
  );
}
