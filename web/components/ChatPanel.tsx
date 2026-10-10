"use client";

import { useEffect, useRef, useState } from "react";
import { getDemoCustomers, getPlays, isMockMode, sendChat } from "../lib/api";
import { toApiError, type ApiError } from "../lib/apiError";
import { CHAT_REQUEST_EVENT, DEMO_CUSTOMER_ID, DEMO_MESSAGE, type ChatRequestDetail } from "../lib/chatBridge";
import { langAttr, languageName, replyLanguage, uniqueByLabel, containsKannada } from "../lib/lang";
import { label as idLabel } from "../lib/labels";
import { prefersReducedMotion } from "../lib/motion";
import { personaCaption } from "../lib/playText";
import { recordOffer, useProgress } from "../lib/progressStore";
import { treatedCustomerFor } from "../lib/treatedPersona";
import { Badge } from "./Badge";
import { Details } from "./Details";
import { ErrorCard } from "./ErrorCard";
import styles from "./ChatPanel.module.css";
import type { ChatEnvelope, DemoCustomer, Play } from "../lib/types";

interface DisplayMessage extends ChatEnvelope {
  key: string;
  /** The visitor's own bubbles only: shown at once ("pending"), then confirmed or marked failed. */
  status?: "pending" | "sent" | "failed";
  /** Agent bubbles with an English gloss: whether the gloss is open. */
  glossShown?: boolean;
}

/** Shown in the log before anything was said (design_spec.md 8.5). */
const EMPTY_TEXT = 'No messages yet. Try "Any offers today?"';

export function ChatPanel({
  title = "Chat as",
  initialMessage = DEMO_MESSAGE,
  suggestedChip = "Do you have Cola Zero?",
  compact = false,
  customerId = DEMO_CUSTOMER_ID,
  showCustomerPicker = true,
  play = null,
}: {
  title?: string;
  customerId?: string;
  initialMessage?: string;
  suggestedChip?: string;
  compact?: boolean;
  showCustomerPicker?: boolean;
  /** The hero play, when the page has one: the caption under the picker is derived from it. */
  play?: Play | null;
}) {
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  // False until the customer list has answered (a cold API can take 3 to 4 s), so the picker's
  // place says "Loading customers…" instead of being blank.
  const [customersLoaded, setCustomersLoaded] = useState(false);
  const [activeId, setActiveId] = useState(customerId);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState(initialMessage);
  const [sending, setSending] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const [chatError, setChatError] = useState<ApiError | null>(null);
  // The last message that failed, so Retry re-sends it without adding a second bubble for it.
  const lastFailed = useRef<{ text: string; shown: string; key: string } | null>(null);
  // The first Kannada reply of a session opens its English line; after that the visitor's own choice
  // (Show or Hide English on any bubble) is the default for the replies that follow. In memory only.
  const glossDefault = useRef(true);
  const listRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // The play whose audience the panel follows: the page's hero play, or (on /chat, which has none)
  // the play this visitor approved last. Once it is approved the panel opens on a customer who is in
  // its audience, because the first customer is only in the chips audience.
  const { crumbs } = useProgress();
  const lastApproved = crumbs.approved[crumbs.approved.length - 1] ?? null;
  const [approvedPlay, setApprovedPlay] = useState<Play | null>(null);
  useEffect(() => {
    if (play || !lastApproved) {
      setApprovedPlay(null);
      return;
    }
    let cancelled = false;
    getPlays({ gap_id: lastApproved.gap_id })
      .then((list) => {
        if (!cancelled) setApprovedPlay(list.find((p) => p.play_id === lastApproved.play_id) ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [play, lastApproved?.play_id, lastApproved?.gap_id]);
  const followedPlay = play ?? approvedPlay;
  const approved =
    followedPlay !== null && (followedPlay.status === "approved" || crumbs.approved.some((a) => a.play_id === followedPlay.play_id));

  const playId = followedPlay?.play_id;
  useEffect(() => {
    if (!showCustomerPicker) return;
    getDemoCustomers(playId)
      .then(setCustomers)
      .catch(() => setCustomers([]))
      .finally(() => setCustomersLoaded(true));
  }, [showCustomerPicker, playId]);

  // One session per demo customer; the per-visitor sandbox (X-Taal-Visitor) keeps judges apart.
  // Switching customer starts a fresh conversation, since it is a different person.
  const sessionId = useRef(`${activeId}:web`);
  const switchRef = useRef<(id: string) => void>(() => {});
  function switchCustomer(id: string) {
    setActiveId(id);
    sessionId.current = `${id}:web`;
    setMessages([]);
    setLatency(null);
    setChatError(null);
    lastFailed.current = null;
  }

  switchRef.current = switchCustomer;
  // True once the visitor (or a follow-up button) chose a customer: the default below never overrides it.
  const chosen = useRef(false);
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;

  // After the play is approved, open on a customer who is in its audience.
  useEffect(() => {
    if (!approved || !followedPlay || customers.length === 0 || chosen.current) return;
    const treated = treatedCustomerFor(followedPlay, customers, activeIdRef.current);
    if (treated && treated.customer_id !== activeIdRef.current) switchRef.current(treated.customer_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approved, followedPlay?.play_id, customers]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  // The Approve result's follow-up buttons (lib/chatBridge.ts), and the same two actions arriving
  // as /chat?as=... from a page that has no chat panel. The latest `send` is kept in a ref so the
  // listener, registered once, never calls a stale one.
  const sendRef = useRef(send);
  sendRef.current = send;
  const holdoutId = customers.find((c) => c.role === "holdout")?.customer_id;
  const holdoutRef = useRef(holdoutId);
  holdoutRef.current = holdoutId;

  useEffect(() => {
    function reveal() {
      rootRef.current?.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    }
    function onRequest(e: Event) {
      const detail = (e as CustomEvent<ChatRequestDetail>).detail;
      if (!detail) return;
      if (detail.action === "prefill") {
        detail.handled = true;
        reveal();
        if (detail.customerId && detail.customerId !== activeIdRef.current) {
          chosen.current = true;
          switchRef.current(detail.customerId);
        }
        setInput(detail.message);
        inputRef.current?.focus({ preventScroll: true });
      } else if (detail.action === "holdout" && holdoutRef.current) {
        detail.handled = true;
        reveal();
        chosen.current = true;
        switchRef.current(holdoutRef.current);
        sendRef.current(detail.message);
      }
    }
    window.addEventListener(CHAT_REQUEST_EVENT, onRequest);
    return () => window.removeEventListener(CHAT_REQUEST_EVENT, onRequest);
  }, []);

  // /chat?as=holdout (or prefill): applied once, when the customer list is in.
  const pendingAs = useRef<string | null>(null);
  const pendingCustomer = useRef<string | null>(null);
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      pendingAs.current = params.get("as");
      pendingCustomer.current = params.get("customer");
    } catch {
      pendingAs.current = null;
    }
  }, []);
  useEffect(() => {
    const as = pendingAs.current;
    if (!as || customers.length === 0) return;
    pendingAs.current = null;
    if (as === "holdout" && holdoutId) {
      chosen.current = true;
      switchRef.current(holdoutId);
      sendRef.current(DEMO_MESSAGE);
    } else if (as === "prefill") {
      const wanted = pendingCustomer.current;
      if (wanted && wanted !== activeIdRef.current && customers.some((c) => c.customer_id === wanted && c.role !== "holdout")) {
        chosen.current = true;
        switchRef.current(wanted);
      }
      setInput(DEMO_MESSAGE);
      inputRef.current?.focus({ preventScroll: true });
    }
  }, [customers, holdoutId]);

  const active = customers.find((c) => c.customer_id === activeId);
  const displayName = active?.display_name ?? "Meena";

  // `text` is what the API receives; `shown` is what the visitor's bubble says. A quick-reply sends its
  // internal payload ("add:SKU-...") but the bubble shows the button's label. The bubble appears at
  // once as "pending"; the first reply confirms it, a failure marks it "not delivered" and offers Retry.
  async function send(text: string, shown: string = text, retryKey?: string) {
    if (!text.trim()) return;
    if (sending) return;
    setSending(true);
    setChatError(null);
    const key = retryKey ?? `u-${Date.now()}-${Math.random()}`;
    if (retryKey) {
      setMessages((prev) => prev.map((m) => (m.key === key ? { ...m, status: "pending" } : m)));
    } else {
      setMessages((prev) => [
        ...prev,
        { key, session_id: sessionId.current, role: "customer", text: shown, status: "pending" },
      ]);
      setInput("");
    }
    const customerLanguage = customers.find((c) => c.customer_id === activeId)?.language;
    try {
      await sendChat(
        {
          session_id: sessionId.current,
          text,
        },
        (envelope, latencyMs) => {
          if (envelope.role === "agent") recordOffer(); // a reply came back: the stepper's Offer step
          setLatency(latencyMs);
          const hasGloss = Boolean(envelope.english_gloss) && replyLanguage(envelope.text, customerLanguage) === "kannada";
          setMessages((prev) => [
            ...prev.map((m) => (m.key === key ? { ...m, status: "sent" as const } : m)),
            {
              key: `a-${Date.now()}-${Math.random()}`,
              ...envelope,
              ...(hasGloss ? { glossShown: glossDefault.current } : {}),
            },
          ]);
        },
      );
      lastFailed.current = null;
    } catch (e) {
      lastFailed.current = { text, shown, key };
      setMessages((prev) => prev.map((m) => (m.key === key ? { ...m, status: "failed" as const } : m)));
      setChatError(toApiError(e, "/chat"));
    } finally {
      setSending(false);
    }
  }

  function toggleGloss(key: string) {
    const current = messages.find((m) => m.key === key);
    if (!current) return;
    const next = !current.glossShown;
    glossDefault.current = next;
    setMessages((prev) => prev.map((m) => (m.key === key ? { ...m, glossShown: next } : m)));
  }

  const customerLanguage = active?.language;

  return (
    <div ref={rootRef} id="chat-panel" className={`chat-panel ${compact ? "chat-panel--compact" : ""}`}>
      <div className="chat-panel__header">
        <h3>{title} {displayName}</h3>
        <div className="chat-panel__badges">
          <Badge kind={isMockMode() ? "replay" : "live"} />
          {latency !== null ? <span className="chip">{latency} ms</span> : null}
        </div>
      </div>
      {showCustomerPicker && !customersLoaded ? (
        <p className="muted chat-panel__customer-note" data-testid="chat-customers-loading" role="status">
          Loading customers…
        </p>
      ) : null}
      {showCustomerPicker && customers.length > 0 ? (
        <div className="chat-panel__customer-picker">
          <label>
            Customer{" "}
            <select
              value={activeId}
              onChange={(e) => {
                chosen.current = true;
                switchCustomer(e.target.value);
              }}
              className={styles.picker}
              data-testid="chat-customer-select"
            >
              {customers.map((c) => (
                <option key={c.customer_id} value={c.customer_id}>
                  {customerOptionLabel(c)}
                </option>
              ))}
            </select>
          </label>
          {active ? (
            <p className="muted chat-panel__customer-note" data-testid="chat-customer-note">
              {personaCaption(active, followedPlay)}
            </p>
          ) : null}
          {active ? (
            <div className={styles.pickerDetails}>
              <Details summary="Details" testId="chat-customer-ids">
                {active.customer_id} · {active.home_node_id} · {active.language}
              </Details>
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="chat-panel__list" ref={listRef} data-testid="chat-log" role="log" aria-live="polite">
        {messages.length === 0 ? <p className="muted">{EMPTY_TEXT}</p> : null}
        {messages.map((m) => {
          const isAgent = m.role === "agent";
          const language = isAgent ? replyLanguage(m.text, customerLanguage) : null;
          const bubbleClass = `chat-msg chat-msg--${m.role}${m.status === "pending" ? ` ${styles.pending}` : ""}${m.status === "failed" ? ` ${styles.failed}` : ""}`;
          const buttons = m.buttons ? uniqueByLabel(m.buttons) : null;
          const glossId = `gloss-${m.key}`;
          return (
            <div key={m.key} className={bubbleClass} data-status={m.status}>
              {language === "english_fallback" ? (
                <span className={styles.tag} data-testid="english-fallback-label" title="The Kannada reply was not available, so this is the English version.">
                  English fallback
                  <span className="visually-hidden">: the Kannada reply was not available, so this is the English version.</span>
                </span>
              ) : null}
              <p lang={language ? langAttr(language) : undefined}>{m.text}</p>
              {buttons ? (
                <div className={`chat-msg__buttons ${styles.tapRow}`}>
                  {buttons.map((b) => (
                    <button
                      key={b.id}
                      type="button"
                      lang={containsKannada(b.label) ? "kn" : undefined}
                      onClick={() => send(b.id, b.label)}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              ) : null}
              {m.list ? (
                <div className="chat-msg__list">
                  <p className="chat-msg__list-title">{m.list.title}</p>
                  <ul>
                    {m.list.rows.map((row) => (
                      <li key={row.id}>
                        <button type="button" className="chat-msg__list-item" onClick={() => send(row.id, row.title)} disabled={sending}>
                          <strong>{row.title}</strong>
                          {row.desc ? <span>&nbsp;— {row.desc}</span> : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {isAgent && m.english_gloss && language === "kannada" ? (
                <>
                  {m.glossShown ? (
                    <p id={glossId} className="chat-msg__gloss" lang="en" data-testid="english-gloss">
                      {m.english_gloss}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    className={styles.glossToggle}
                    aria-expanded={Boolean(m.glossShown)}
                    aria-controls={m.glossShown ? glossId : undefined}
                    onClick={() => toggleGloss(m.key)}
                    data-testid="gloss-toggle"
                  >
                    {m.glossShown ? "Hide English" : "Show English"}
                  </button>
                </>
              ) : isAgent && m.english_gloss ? (
                <p className="chat-msg__gloss" lang="en" data-testid="english-gloss">
                  {m.english_gloss}
                </p>
              ) : null}
              {m.citations && m.citations.length > 0 ? (
                <div className={styles.sources}>
                  <Details summary="Sources" testId="chat-sources">
                    {m.citations.map((c) => c.ref).join(", ")}
                  </Details>
                </div>
              ) : null}
            </div>
          );
        })}
        {sending ? <p className="muted">{displayName} is typing…</p> : null}
        {chatError ? (
          <ErrorCard
            error={chatError}
            compact
            onRetry={() => {
              const failed = lastFailed.current;
              if (failed) send(failed.text, failed.shown, failed.key);
            }}
          />
        ) : null}
      </div>
      <div className={`${styles.suggestions} ${styles.tapRow}`}>
        <button type="button" onClick={() => send(suggestedChip)} disabled={sending}>
          {suggestedChip}
        </button>
      </div>
      <form
        className={`chat-panel__composer ${styles.tapRow} ${styles.composer}`}
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-label="Message"
          placeholder="Type a message…"
          autoComplete="off"
        />
        <button type="submit" disabled={sending}>Send</button>
        <button
          type="button"
          className={`chat-panel__stop ${styles.stop}`}
          onClick={() => send("STOP")}
          disabled={sending}
          title="Sends the STOP message as the customer, to show what happens when someone opts out."
          aria-describedby="chat-stop-hint"
        >
          Customer replies STOP (opt-out demo)
        </button>
        <span id="chat-stop-hint" className="visually-hidden">
          Sends the STOP message as the customer, to show what happens when someone opts out.
        </span>
      </form>
    </div>
  );
}

/** "Meena, Dark store 7 (Kannada)": a person, where they shop and the language they read. No ids. */
function customerOptionLabel(c: DemoCustomer): string {
  const where = idLabel("node", c.home_node_id);
  const language = languageName(c.language);
  return `${c.display_name}, ${where} (${language}${c.role === "holdout" ? ", holdout" : ""})`;
}
