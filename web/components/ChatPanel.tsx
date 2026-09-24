"use client";

import { useEffect, useRef, useState } from "react";
import { getDemoCustomers, isMockMode, sendChat } from "../lib/api";
import { swatchFor } from "../lib/colour";
import { GarmentGlyph, iconKeyFor } from "../lib/garmentArt";
import { Badge } from "./Badge";
import type { ChatEnvelope, DemoCustomer } from "../lib/types";

interface DisplayMessage extends ChatEnvelope {
  key: string;
  photoDataUrl?: string;
  photoName?: string;
}

interface PendingPhoto {
  dataUrl?: string;
  photoRef?: string;
  kind: "garment" | "selfie";
  name: string;
}

const SAMPLE_GARMENTS = [
  { ref: "fixtures/photos/garments/mustard_kurta.png", label: "Mustard kurta" },
  { ref: "fixtures/photos/garments/navy_tshirt.png", label: "Navy T-shirt" },
  { ref: "fixtures/photos/garments/red_floral_dress.png", label: "Red floral dress" },
];

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
      {
        key: `u-${Date.now()}`,
        session_id: sessionId.current,
        role: "customer",
        text: text || (photo ? `[photo: ${photo.name}]` : ""),
        photoDataUrl: photo?.dataUrl,
        photoName: photo?.name,
      },
    ]);
    setInput("");
    setPendingPhoto(null);
    try {
      await sendChat(
        {
          session_id: sessionId.current,
          text,
          specialist,
          ...(photo?.photoRef
            ? { photo_ref: photo.photoRef, image_kind: photo.kind }
            : photo?.dataUrl
              ? { image_data_url: photo.dataUrl, image_kind: photo.kind }
              : {}),
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

  function pickSampleGarment(ref: string, label: string) {
    setPendingPhoto({ photoRef: ref, kind: "garment", name: label });
  }

  return (
    <div className={`chat-panel ${compact ? "chat-panel--compact" : ""}`}>
      <div className="chat-panel__header">
        <h3>{title} {displayName}</h3>
        <div className="chat-panel__badges">
          <Badge kind={isMockMode() ? "replay" : "live"} title={`Chat as ${displayName}`} />
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
            {m.photoDataUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="chat-msg__photo" src={m.photoDataUrl} alt={m.photoName ?? "Attached photo"} />
            ) : m.photoName ? (
              <p className="chat-msg__photo-label muted">📷 {m.photoName}</p>
            ) : null}
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
                  {m.list.rows.map((row) => {
                    const swatch = specialist === "stylist" ? swatchFor(row.title) : null;
                    const hasGlyph = specialist === "stylist" && !!iconKeyFor(row.garment_type, null);
                    return (
                      <li key={row.id}>
                        <button type="button" className="chat-msg__list-item" onClick={() => send(row.id)} disabled={sending}>
                          {hasGlyph ? (
                            <span className="chat-msg__glyph-wrap" style={{ color: swatch ?? undefined }}>
                              <GarmentGlyph garmentType={row.garment_type} hex={swatch} />
                            </span>
                          ) : swatch ? (
                            <span className="chat-msg__swatch" style={{ background: swatch }} aria-hidden="true" />
                          ) : null}
                          <strong>{row.title}</strong>
                          {row.desc ? <span>&nbsp;— {row.desc}</span> : null}
                        </button>
                      </li>
                    );
                  })}
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
          <p className="muted chat-panel__photo-note">Use a sample garment photo</p>
          <div className="photo-choices" data-testid="sample-garment-choices">
            {SAMPLE_GARMENTS.map((g) => (
              <button
                key={g.ref}
                type="button"
                className="photo-choice"
                aria-pressed={pendingPhoto?.photoRef === g.ref}
                onClick={() => pickSampleGarment(g.ref, g.label)}
              >
                {g.label}
              </button>
            ))}
          </div>
          <label className="camera-button">
            <span className="camera-button__icon" aria-hidden="true">📷</span>
            <span>Own garment photo (experimental)</span>
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
