"use client";

import { useEffect, useRef, useState } from "react";
import { getDemoCustomers, isMockMode, sendChat } from "../lib/api";
import { Badge } from "./Badge";
import type { ChatEnvelope, DemoCustomer } from "../lib/types";

interface DisplayMessage extends ChatEnvelope {
  key: string;
}

interface PendingPhoto {
  dataUrl: string;
  kind: "garment" | "selfie";
  name: string;
}

export function ChatPanel({
  title = "Chat as",
  initialMessage = "Any offers today?",
  suggestedChip = "Do you have Cola Zero?",
  compact = false,
  customerId = "CUST-MEENA",
  showCustomerPicker = true,
  specialist = "customer",
}: {
  title?: string;
  customerId?: string;
  initialMessage?: string;
  suggestedChip?: string;
  compact?: boolean;
  showCustomerPicker?: boolean;
  specialist?: "customer" | "stylist";
}) {
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [activeId, setActiveId] = useState(customerId);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState(initialMessage);
  const [sending, setSending] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const [pendingPhoto, setPendingPhoto] = useState<PendingPhoto | null>(null);
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
    setPendingPhoto(null);
  }

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  const active = customers.find((c) => c.customer_id === activeId);
  const displayName = active?.display_name ?? "Meena";

  async function send(text: string) {
    const photo = pendingPhoto;
    if (!text.trim() && !photo) return;
    if (sending) return;
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { key: `u-${Date.now()}`, session_id: sessionId.current, role: "customer", text: text || (photo ? `[photo: ${photo.name}]` : "") },
    ]);
    setInput("");
    setPendingPhoto(null);
    try {
      await sendChat(
        {
          session_id: sessionId.current,
          text,
          specialist,
          ...(photo ? { image_data_url: photo.dataUrl, image_kind: photo.kind } : {}),
        },
        (envelope, latencyMs) => {
          setLatency(latencyMs);
          setMessages((prev) => [...prev, { key: `a-${Date.now()}-${Math.random()}`, ...envelope }]);
        },
      );
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

  function onPhotoFile(kind: "garment" | "selfie") {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => setPendingPhoto({ dataUrl: reader.result as string, kind, name: file.name });
      reader.readAsDataURL(file);
      e.target.value = "";
    };
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
                      <button type="button" className="chat-msg__list-item" onClick={() => send(row.id)} disabled={sending}>
                        <strong>{row.title}</strong>
                        {row.desc ? <span> — {row.desc}</span> : null}
                      </button>
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
      {specialist === "stylist" ? (
        <div className="chat-panel__photo-inputs">
          <label className="camera-button">
            <span className="camera-button__icon" aria-hidden="true">📷</span>
            <span>Garment photo</span>
            <input type="file" accept="image/*" onChange={onPhotoFile("garment")} aria-label="Garment photo" data-testid="garment-photo" />
          </label>
          <label className="camera-button">
            <span className="camera-button__icon" aria-hidden="true">🙂</span>
            <span>Selfie for skin tone</span>
            <input type="file" accept="image/*" onChange={onPhotoFile("selfie")} aria-label="Selfie for skin tone" data-testid="selfie-photo" />
          </label>
          {pendingPhoto ? (
            <span className="chip chat-panel__photo-chip">
              {pendingPhoto.kind === "selfie" ? "Selfie" : "Photo"} attached: {pendingPhoto.name}
              <button type="button" onClick={() => setPendingPhoto(null)} aria-label="Remove photo">×</button>
            </span>
          ) : null}
          <p className="muted chat-panel__photo-note">
            A selfie is used once to guess your undertone; the photo itself is never kept. You confirm before anything is saved. Say &quot;forget my skin tone&quot; any time.
          </p>
        </div>
      ) : null}
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
        {specialist === "customer" ? (
          <button type="button" className="chat-panel__stop" onClick={() => send("STOP")} disabled={sending}>
            STOP
          </button>
        ) : null}
      </form>
    </div>
  );
}
