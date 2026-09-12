"use client";

import { Fragment, useMemo, useState } from "react";
import { ApprovePanel } from "../../components/ApprovePanel";
import { Badge } from "../../components/Badge";
import { GapCard } from "../../components/GapCard";
import { capture, captureConfirm, execution, getGaps, getPlays } from "../../lib/api";
import type { ApproveResponse, ExecutionStep, Gap, Mechanic, Play, VisionRow } from "../../lib/types";

const NODES = ["DS-07", "DS-04", "DS-01"];
const SAMPLE_PHOTOS = [
  { ref: "fixtures/photos/pallet_01.jpg", label: "Pallet 1" },
  { ref: "fixtures/photos/pallet_02.jpg", label: "Pallet 2" },
  { ref: "fixtures/photos/pallet_03.jpg", label: "Pallet 3" },
];

function stepsForMechanic(mechanic: Mechanic): ExecutionStep[] {
  if (mechanic === "transfer_plus_nudge") {
    return [
      { id: "move", text: "Move units to outlet" },
      { id: "tag", text: "Print shelf tag" },
      { id: "photo", text: "Photograph shelf" },
    ];
  }
  return [
    { id: "print", text: "Print offer tag" },
    { id: "place", text: "Place at shelf" },
  ];
}

export default function PhoneViewPage() {
  const [nodeId, setNodeId] = useState("DS-07");
  const [selectedPhoto, setSelectedPhoto] = useState<string | null>(null);
  const [ownFileName, setOwnFileName] = useState<string | null>(null);
  const [rows, setRows] = useState<VisionRow[] | null>(null);
  const [confirmed, setConfirmed] = useState<Record<number, boolean>>({});
  const [capturing, setCapturing] = useState(false);
  const [gap, setGap] = useState<Gap | null>(null);
  const [play, setPlay] = useState<Play | null>(null);
  const [approveResult, setApproveResult] = useState<ApproveResponse | null>(null);
  const [stepsDone, setStepsDone] = useState<Record<string, boolean>>({});
  const [executionSaved, setExecutionSaved] = useState(false);

  const steps = useMemo(() => (play ? stepsForMechanic(play.mechanic) : []), [play]);

  async function runCapture(photoRef?: string, imageDataUrl?: string) {
    setCapturing(true);
    try {
      const res = await capture({ node_id: nodeId, photo_ref: photoRef, image_data_url: imageDataUrl });
      setRows(res.rows);
      setConfirmed({});
    } finally {
      setCapturing(false);
    }
  }

  function pickSample(ref: string) {
    setSelectedPhoto(ref);
    setOwnFileName(null);
    runCapture(ref);
  }

  function onOwnFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setOwnFileName(file.name);
    setSelectedPhoto(null);
    const reader = new FileReader();
    reader.onload = () => {
      runCapture(undefined, reader.result as string);
    };
    reader.readAsDataURL(file);
  }

  async function loadGapForNode() {
    if (rows && selectedPhoto) {
      const confirmedRows = rows.map((r, i) => ({ ...r, confirmed: confirmed[i] === true }));
      await captureConfirm({ node_id: nodeId, photo_ref: selectedPhoto, rows: confirmedRows });
    }
    const [gaps, plays] = await Promise.all([getGaps({ node_id: nodeId }), getPlays()]);
    // Gaps for the SKUs just read from the pallet come first, then the rest by rupees at stake.
    const photoSkus = new Set((rows ?? []).map((r) => r.sku_guess));
    const ordered = [...gaps].sort((a, b) => Number(photoSkus.has(b.sku)) - Number(photoSkus.has(a.sku)));
    const topGap = ordered[0] ?? null;
    setGap(topGap);
    if (topGap) {
      const matching = plays.filter((p) => p.gap_id === topGap.gap_id);
      setPlay(matching[0] ?? null);
    } else {
      setPlay(null);
    }
  }

  function toggleStep(id: string) {
    setStepsDone((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  async function markDone() {
    if (!play) return;
    await execution({
      play_id: play.play_id,
      node_id: nodeId,
      steps_done: steps.filter((s) => stepsDone[s.id]).map((s) => s.id),
    });
    setExecutionSaved(true);
  }

  const allConfirmable = rows?.every((r, i) => !r.needs_confirmation || confirmed[i] !== undefined) ?? false;

  return (
    <main className="page">
      <h2>Priya's phone</h2>

      <section className="card">
        <label>
          Node{" "}
          <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
            {NODES.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <h4>Use a sample pallet photo</h4>
        <div className="photo-choices">
          {SAMPLE_PHOTOS.map((p) => (
            <button
              key={p.ref}
              type="button"
              className="photo-choice"
              aria-pressed={selectedPhoto === p.ref}
              onClick={() => pickSample(p.ref)}
            >
              {p.label}
            </button>
          ))}
        </div>

        <p className="muted">Own photo (experimental)</p>
        <input type="file" accept="image/*" onChange={onOwnFile} aria-label="Own photo (experimental)" />
        {ownFileName ? <p className="muted">Selected: {ownFileName}</p> : null}

        <button type="button" className="mic-button" disabled title="Voice: Live API session, documented stub" aria-label="Voice input (disabled)">
          🎤
        </button>

        {capturing ? <p className="muted">Reading pallet…</p> : null}

        {rows ? (
          <>
            <table className="intake-table" data-testid="intake-table">
              <thead>
                <tr>
                  <th>SKU guess</th>
                  <th>Best before</th>
                  <th>Facings</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <Fragment key={`frag-${i}`}>
                    <tr key={`row-${i}`}>
                      <td>{row.sku_guess}</td>
                      <td>{row.best_before_date ?? "–"}</td>
                      <td>{row.facings_count}</td>
                      <td>
                        sku {Math.round(row.sku_confidence * 100)}% · date {Math.round(row.date_confidence * 100)}% ·
                        count {Math.round(row.count_confidence * 100)}%
                      </td>
                    </tr>
                    {row.needs_confirmation ? (
                      <tr key={`confirm-${i}`} className="confirm-row">
                        <td colSpan={4}>
                          <p>{row.confirmation_question}</p>
                          <button type="button" onClick={() => setConfirmed((c) => ({ ...c, [i]: true }))}>
                            {confirmed[i] === true ? "Confirmed: Yes" : "Yes"}
                          </button>{" "}
                          <button type="button" onClick={() => setConfirmed((c) => ({ ...c, [i]: false }))}>
                            {confirmed[i] === false ? "Confirmed: No" : "No"}
                          </button>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <button type="button" onClick={loadGapForNode} disabled={!allConfirmable}>
              Confirm rows
            </button>
          </>
        ) : null}
      </section>

      {gap ? (
        <section>
          <GapCard gap={gap} />
          {play ? (
            <div className="card">
              <div className="card__header">
                <h3>Play: {play.mechanic}</h3>
                <Badge kind="replay" detail="pre-proposed" />
              </div>
              <p>{play.rationale.split(".")[0]}.</p>
              <ApprovePanel play={play} onApproved={setApproveResult} />
            </div>
          ) : null}
        </section>
      ) : null}

      {approveResult && play ? (
        <section className="card">
          <h4>Execution steps</h4>
          <ul className="execution-steps">
            {steps.map((s) => (
              <li key={s.id}>
                <input
                  type="checkbox"
                  checked={!!stepsDone[s.id]}
                  onChange={() => toggleStep(s.id)}
                  id={`step-${s.id}`}
                />
                <label htmlFor={`step-${s.id}`}>{s.text}</label>
              </li>
            ))}
          </ul>
          <button type="button" onClick={markDone}>Done</button>
          {executionSaved ? <p className="muted">Execution recorded.</p> : null}
        </section>
      ) : null}
    </main>
  );
}
