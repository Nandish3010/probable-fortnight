"use client";

import { useState } from "react";
import Link from "next/link";
import { ApprovePanel } from "../components/ApprovePanel";
import { Badge } from "../components/Badge";
import { ChatPanel } from "../components/ChatPanel";
import { GapCard } from "../components/GapCard";
import { HealthStrip, TenantLine } from "../components/HealthStrip";
import { getGaps, getPlays, resetDemoData } from "../lib/api";
import type { Gap, Play } from "../lib/types";

const CHIPS_GAP_ID = "gap_chips_ds07";

export default function LandingPage() {
  const [beatStarted, setBeatStarted] = useState(false);
  const [gap, setGap] = useState<Gap | null>(null);
  const [play, setPlay] = useState<Play | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetNote, setResetNote] = useState<string | null>(null);

  async function runTheBeat() {
    setBeatStarted(true);
    const [gaps, plays] = await Promise.all([
      getGaps(),
      getPlays({ gap_id: CHIPS_GAP_ID }),
    ]);
    setGap(gaps.find((g) => g.gap_id === CHIPS_GAP_ID) ?? gaps[0] ?? null);
    setPlay(plays[0] ?? null);
  }

  async function handleReset() {
    setResetting(true);
    try {
      const res = await resetDemoData();
      setResetNote(`Reset done for visitor ${res.namespace.slice(0, 8)}…`);
      setBeatStarted(false);
      setGap(null);
      setPlay(null);
    } finally {
      setResetting(false);
    }
  }

  return (
    <main className="page">
      <section className="judge-band">
        <span>
          Taal judge mode: seeded tenant Kutumb Mart. Nothing you do here persists beyond your session.
        </span>
        <button type="button" onClick={handleReset} disabled={resetting}>
          {resetting ? "Resetting…" : "Reset demo data"}
        </button>
      </section>
      {resetNote ? <p className="muted">{resetNote}</p> : null}

      <section className="hero">
        <div className="card">
          <h2>Run the 60-second beat</h2>
          <p className="muted">
            One click opens the chips gap, its pre-proposed play, and stops at Approve.
          </p>
          {!beatStarted ? (
            <button type="button" className="hero__cta" onClick={runTheBeat}>
              Run the 60-second beat
            </button>
          ) : !gap || !play ? (
            <p className="muted">Loading gap and play…</p>
          ) : (
            <div data-testid="beat-panel">
              <GapCard gap={gap} />
              <div className="card" data-testid="play-card">
                <div className="card__header">
                  <h3>Pre-proposed play: {play.mechanic}</h3>
                  <Badge kind="replay" detail="Planner run recorded" />
                </div>
                <p>{play.rationale}</p>
                <ApprovePanel play={play} />
              </div>
            </div>
          )}
        </div>

        <ChatPanel />
      </section>

      <section className="card-grid">
        <Link className="card-link" href="/desk">
          <div className="card">
            <div className="card__header">
              <h3>Play Desk</h3>
              <Badge kind="live" detail="live reads" />
            </div>
            <p className="muted">Inbox ranked by rupees at stake, guardrails, trace, policy editor.</p>
          </div>
        </Link>
        <Link className="card-link" href="/phone">
          <div className="card">
            <div className="card__header">
              <h3>Phone view</h3>
              <Badge kind="replay" detail="sample pallet photo" />
            </div>
            <p className="muted">Priya's capture-to-approve flow. Own upload is experimental.</p>
          </div>
        </Link>
        <Link className="card-link" href="/outcomes">
          <div className="card">
            <div className="card__header">
              <h3>Outcomes</h3>
              <Badge kind="real-pilot" detail="computed 3 Oct" />
            </div>
            <p className="muted">Treated vs holdout, the CEO number, unmeasured plays.</p>
          </div>
        </Link>
      </section>

      <footer className="footer">
        <div className="footer__links">
          <a href="#">Video (2:40)</a>
          <a href="#">Deck</a>
          <a href="#">Repo</a>
        </div>
        <div className="sim-box">
          <strong>What is simulated:</strong> catalogue, sales history, stock and customers are a seeded
          synthetic tenant. <strong>What is real:</strong> forecasts, agents, guardrails, holdout and
          measurement are real code paths.
        </div>
        <TenantLine />
        <HealthStrip />
      </footer>
    </main>
  );
}
