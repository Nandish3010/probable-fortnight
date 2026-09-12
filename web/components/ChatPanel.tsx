"use client";

import { useEffect, useRef, useState } from "react";
import { getDemoCustomers, isMockMode, sendChat } from "../lib/api";
import { Badge } from "./Badge";
import type { ChatEnvelope, DemoCustomer } from "../lib/types";

interface DisplayMessage extends ChatEnvelope {
  key: string;
}

export function ChatPanel({
  title = "Chat as",
  initialMessage = "Any offers today?",
  suggestedChip = "Do you have Cola Zero?",
  compact = false,
  customerId = "CUST-MEENA",
  showCustomerPicker = true,
}: {
  title?: string;
  customerId?: string;
  initialMessage?: string;
  suggestedChip?: string;
  compact?: boolean;
  showCustomerPicker?: boolean;
}) {
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [activeId, setActiveId] = useState(customerId);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState(initialMessage);
  const [sending, setSending] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showCustomerPicker) return;
    getDemoCustomers().then(setCustomers).catch(() => setCustomers([]));
  }, [showCustomerPicker]);

  // One session per demo customer; the per-visitor sandbox (X-Taal-Visitor) keeps judges apart.
  // Switching customer starts a fresh conversation, since it is a different person.
  const sessionId = useRef(`${activeId}:web`);
  function switchCustomer(id: string) {
    setActiveId(id);
    sessionId.current = `${id}:web`;
    setMessages([]);
    setLatency(null);
  }

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  const active = customers.find((c) => c.customer_id === activeId);
  const displayName = active?.display_name ?? "Meena";

  async function send(text: string) {
    if (!text.trim() || sending) return;
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { key: `u-${Date.now()}`, session_id: sessionId.current, role: "customer", text },
    ]);
    setInput("");
    try {
      await sendChat({ session_id: sessionId.current, text }, (envelope, latencyMs) => {
        setLatency(latencyMs);
        setMessages((prev) => [...prev, { key: `a-${Date.now()}-${Math.random()}`, ...envelope }]);
      });
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          key: `err-${Date.now()}`,
          session_id: sessionId.current,
          role: "system",
          text: "Live call failed; showing recorded result (live call failed).",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={`chat-panel ${compact ? "chat-panel--compact" : ""}`}>
      <div className="chat-panel__header">
        <h3>{title} {displayName}</h3>
        <div className="chat-panel__badges">
          <Badge kind={isMockMode() ? "live" : "live"} title={`Chat as ${displayName}`} />
          {latency !== null ? <span className="chip">{latency} ms</span> : null}
        </div>
      </div>
      {showCustomerPicker && customers.length > 0 ? (
        <div className="chat-panel__customer-picker">
          <label>
            Customer{" "}
            <select
              value={activeId}
              onChange={(e) => switchCustomer(e.target.value)}
              data-testid="chat-customer-select"
            >
              {customers.map((c) => (
                <option key={c.customer_id} value={c.customer_id}>
                  {c.display_name} ({c.home_node_id}, {c.language}{c.role === "holdout" ? " · holdout" : ""})
                </option>
              ))}
            </select>
          </label>
          {active ? <p className="muted chat-panel__customer-note">{active.note}</p> : null}
        </div>
      ) : null}
      <div className="chat-panel__list" ref={listRef} data-testid="chat-log">
        {messages.length === 0 ? <p className="muted">Send a message to start.</p> : null}
        {messages.map((m) => (
          <div key={m.key} className={`chat-msg chat-msg--${m.role}`}>
            <p>{m.text}</p>
            {m.buttons ? (
              <div className="chat-msg__buttons">
                {m.buttons.map((b) => (
                  <button key={b.id} type="button" onClick={() => send(b.id)}>
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
                      <strong>{row.title}</strong>
                      {row.desc ? <span> — {row.desc}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {m.citations && m.citations.length > 0 ? (
              <p className="chat-msg__citations muted">cited: {m.citations.map((c) => c.ref).join(", ")}</p>
            ) : null}
          </div>
        ))}
        {sending ? <p className="muted">{displayName} is typing…</p> : null}
      </div>
      <div className="chat-panel__suggestions">
        <button type="button" onClick={() => send(suggestedChip)} disabled={sending}>
          {suggestedChip}
        </button>
      </div>
      <form
        className="chat-panel__composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-label="Message"
          placeholder="Type a message…"
        />
        <button type="submit" disabled={sending}>Send</button>
        <button type="button" className="chat-panel__stop" onClick={() => send("STOP")} disabled={sending}>
          STOP
        </button>
      </form>
    </div>
  );
}
