"use client";

import { useEffect, useRef, useState } from "react";
import { isMockMode, sendChat } from "../lib/api";
import { Badge } from "./Badge";
import { getVisitorId } from "../lib/visitor";
import type { ChatEnvelope } from "../lib/types";

interface DisplayMessage extends ChatEnvelope {
  key: string;
}

export function ChatPanel({
  title = "Chat as Meena",
  initialMessage = "Any offers today?",
  suggestedChip = "Do you have Cola Zero?",
  compact = false,
}: {
  title?: string;
  initialMessage?: string;
  suggestedChip?: string;
  compact?: boolean;
}) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState(initialMessage);
  const [sending, setSending] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const sessionId = useRef(`meena-${getVisitorId()}:web`);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

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
        <h3>{title}</h3>
        <div className="chat-panel__badges">
          <Badge kind={isMockMode() ? "live" : "live"} title="Chat as Meena" />
          {latency !== null ? <span className="chip">{latency} ms</span> : null}
        </div>
      </div>
      <div className="chat-panel__list" ref={listRef} data-testid="chat-log">
        {messages.length === 0 ? <p className="muted">Send a message to start.</p> : null}
        {messages.map((m) => (
          <div key={m.key} className={`chat-msg chat-msg--${m.role}`}>
            <p>{m.text}</p>
            {m.buttons ? (
              <div className="chat-msg__buttons">
                {m.buttons.map((b) => (
                  <button key={b.id} type="button" onClick={() => send(b.label)}>
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
        {sending ? <p className="muted">Meena is typing…</p> : null}
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
