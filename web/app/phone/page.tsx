"use client";

import Image from "next/image";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Details } from "../../components/Details";
import { ErrorCard } from "../../components/ErrorCard";
import { GapCard } from "../../components/GapCard";
import { Icon } from "../../components/icons";
import { PlayCard } from "../../components/PlayCard";
import { Skeleton } from "../../components/Skeleton";
import { capture, captureConfirm, execution, getGaps, getPlays, type CaptureConfirmSkip } from "../../lib/api";
import { toApiError, type ApiError } from "../../lib/apiError";
import { label } from "../../lib/labels";
import { prefersReducedMotion } from "../../lib/motion";
import { recordSpot } from "../../lib/progressStore";
import { relativeDate } from "../../lib/format";
import { useServerNow } from "../../lib/useServerNow";
import type { ApproveResponse, ExecutionStep, Gap, Mechanic, Play, VisionRow } from "../../lib/types";

const NODES = ["DS-07", "DS-04", "DS-01"];
// The photo_ref sent to the API is the fixture path the vision backend keys its recorded/live
// read off of (agents/capture/vision.py); the src is this same image copied into web/public/ so
// the browser can actually show it -- the two must stay in sync, one photo per real jpg.
const SAMPLE_PHOTOS = [
  { ref: "fixtures/photos/pallet_01.jpg", src: "/samples/pallet_01.jpg", label: "Pallet 1 · snacks" },
  { ref: "fixtures/photos/pallet_02.jpg", src: "/samples/pallet_02.jpg", label: "Pallet 2 · tea" },
  { ref: "fixtures/photos/pallet_03.jpg", src: "/samples/pallet_03.jpg", label: "Pallet 3 · sweets" },
  { ref: "fixtures/photos/pallet_04.jpg", src: "/samples/pallet_04.jpg", label: "Pallet 4 · rice & dal" },
  { ref: "fixtures/photos/pallet_05.jpg", src: "/samples/pallet_05.jpg", label: "Pallet 5 · oil" },
  { ref: "fixtures/photos/pallet_06.jpg", src: "/samples/pallet_06.jpg", label: "Pallet 6 · atta & poha (date hard to read)" },
  { ref: "fixtures/photos/pallet_08.jpg", src: "/samples/pallet_08.jpg", label: "Pallet 7 · milk & paneer" },
];

/** A confidence under this share is called out (colour, an icon and the word "low"), and the same
 * threshold the server uses to ask for a confirmation. */
const LOW_CONFIDENCE = 0.8;

function Confidence({ name, value }: { name: string; value: number }) {
  const low = value < LOW_CONFIDENCE;
  return (
    <span className={`conf ${low ? "conf--low" : ""}`} data-low={low ? "true" : undefined}>
      {low ? <Icon name="alert-triangle" size={12} /> : null}
      {name} {Math.round(value * 100)}%
      {low ? <span className="visually-hidden"> (low)</span> : null}
    </span>
  );
}

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
  const serverNow = useServerNow();
  const [nodeId, setNodeId] = useState("DS-07");
  const [selectedPhoto, setSelectedPhoto] = useState<string | null>(null);
  const [capturedPhotoRef, setCapturedPhotoRef] = useState<string | null>(null);
  const [ownFileName, setOwnFileName] = useState<string | null>(null);
  // What to actually show above the intake table: the sample's static asset, or the uploaded
  // file's own data URL. Kept separate from photo_ref/selectedPhoto, which are API-facing values.
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [rows, setRows] = useState<VisionRow[] | null>(null);
  const [confirmed, setConfirmed] = useState<Record<number, boolean>>({});
  const [dateOverrides, setDateOverrides] = useState<Record<number, string>>({});
  const [capturing, setCapturing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmSkipped, setConfirmSkipped] = useState<CaptureConfirmSkip[]>([]);
  const [confirmWritten, setConfirmWritten] = useState<number | null>(null);
  const [gap, setGap] = useState<Gap | null>(null);
  const [play, setPlay] = useState<Play | null>(null);
  const [approveResult, setApproveResult] = useState<ApproveResponse | null>(null);
  const [stepsDone, setStepsDone] = useState<Record<string, boolean>>({});
  const [executionSaved, setExecutionSaved] = useState(false);
  // The last failed call and how to run it again; one slot, because the flow is one step at a time.
  const [phoneError, setPhoneError] = useState<{ error: ApiError; retry: () => void } | null>(null);
  // True when no photographed SKU raised a gap and the node's biggest open gap is shown instead.
  const [gapIsFallback, setGapIsFallback] = useState(false);

  const steps = useMemo(() => (play ? stepsForMechanic(play.mechanic) : []), [play]);

  // A tap on a sample tile used to look like nothing happened: the result appears below the tiles,
  // often off screen. Bring it into view and move focus onto it, so a screen reader lands on it too.
  // The table arrives a moment later and makes the page taller; if the visitor has not scrolled in
  // between, the result is brought to the top once more so it really is what they see.
  const resultRef = useRef<HTMLDivElement>(null);
  const userScrolled = useRef(false);
  useEffect(() => {
    const mark = () => {
      userScrolled.current = true;
    };
    window.addEventListener("wheel", mark, { passive: true });
    window.addEventListener("touchmove", mark, { passive: true });
    window.addEventListener("keydown", mark);
    return () => {
      window.removeEventListener("wheel", mark);
      window.removeEventListener("touchmove", mark);
      window.removeEventListener("keydown", mark);
    };
  }, []);
  useEffect(() => {
    if (!previewSrc) return;
    const el = resultRef.current;
    if (!el) return;
    userScrolled.current = false;
    el.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
  }, [previewSrc]);
  useEffect(() => {
    if (!rows || userScrolled.current) return;
    const el = resultRef.current;
    if (el && el.getBoundingClientRect().top > 120) {
      el.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    }
  }, [rows]);

  // Confirm rows removes the button that was pressed; when the gap's card appears and focus has
  // dropped to <body>, put it on the card's title so the next Tab reaches Approve.
  const gapSectionRef = useRef<HTMLElement>(null);
  const cardKey = play ? play.play_id : gap ? gap.gap_id : null;
  useEffect(() => {
    if (!cardKey) return;
    const a = document.activeElement;
    if (a && a !== document.body) return;
    gapSectionRef.current?.querySelector<HTMLElement>("[data-card-title]")?.focus({ preventScroll: true });
  }, [cardKey]);

  async function runCapture(photoRef?: string, imageDataUrl?: string) {
    setCapturing(true);
    setPhoneError(null);
    try {
      const res = await capture({ node_id: nodeId, photo_ref: photoRef, image_data_url: imageDataUrl });
      setRows(res.rows);
      setConfirmed({});
      setDateOverrides({});
      setConfirmSkipped([]);
      setConfirmWritten(null);
      // Track the photo_ref the API actually returned, not the UI's selectedPhoto state --
      // an uploaded photo has no selectedPhoto (that only tracks the sample-photo buttons), so
      // confirm must key off what capture() gave back or it can never be called for an upload.
      setCapturedPhotoRef(res.photo_ref);
    } catch (e) {
      setPhoneError({ error: toApiError(e, "/capture"), retry: () => runCapture(photoRef, imageDataUrl) });
    } finally {
      setCapturing(false);
    }
  }

  function pickSample(ref: string, src: string) {
    setSelectedPhoto(ref);
    setOwnFileName(null);
    setPreviewSrc(src);
    runCapture(ref);
  }

  function onOwnFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setOwnFileName(file.name);
    setSelectedPhoto(null);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setPreviewSrc(dataUrl);
      runCapture(undefined, dataUrl);
    };
    reader.readAsDataURL(file);
  }

  // In-place reset for a live demo: clears the photo/read/gap state on this page without a full
  // navigation, so a fresh "own photo" can be uploaded right away. This is local UI state only --
  // it does not call the server-side /reset (landing page's "Reset demo data"), which clears the
  // per-visitor sandbox's written batches/gaps/plays, a separate and heavier operation.
  function clearPhoto() {
    setSelectedPhoto(null);
    setCapturedPhotoRef(null);
    setOwnFileName(null);
    setPreviewSrc(null);
    setRows(null);
    setConfirmed({});
    setDateOverrides({});
    setConfirmSkipped([]);
    setConfirmWritten(null);
    setGap(null);
    setPlay(null);
    setApproveResult(null);
    setStepsDone({});
    setExecutionSaved(false);
    setPhoneError(null);
    setGapIsFallback(false);
  }

  async function loadGapForNode() {
    setPhoneError(null);
    try {
      await loadGapForNodeUnguarded();
    } catch (e) {
      setPhoneError({ error: toApiError(e, "/capture/confirm"), retry: loadGapForNode });
    }
  }

  async function loadGapForNodeUnguarded() {
    if (rows && capturedPhotoRef) {
      setConfirming(true);
      try {
        const confirmedRows = rows.map((r, i) => ({
          ...r,
          confirmed: confirmed[i] === true,
          best_before_date: dateOverrides[i] || r.best_before_date,
        }));
        const result = await captureConfirm({ node_id: nodeId, photo_ref: capturedPhotoRef, rows: confirmedRows });
        setConfirmWritten(result.written);
        setConfirmSkipped(result.skipped);
        if (!result.ok) {
          // Nothing was written -- do not proceed to load gaps as if the confirm succeeded.
          return;
        }
        recordSpot(); // Priya's rows are in: the stepper's Spot step
      } finally {
        setConfirming(false);
      }
    }
    const [gaps, plays] = await Promise.all([getGaps({ node_id: nodeId }), getPlays()]);
    // Gaps for the SKUs just read from the pallet come first, then the rest by rupees at stake.
    const photoSkus = new Set((rows ?? []).map((r) => r.sku_guess));
    const ordered = [...gaps].sort((a, b) => Number(photoSkus.has(b.sku)) - Number(photoSkus.has(a.sku)));
    const topGap = ordered[0] ?? null;
    // No photographed SKU raised a gap: the card below is the node's biggest open gap, not
    // something read off the pallet, and the page says so.
    setGapIsFallback(topGap !== null && (rows ?? []).length > 0 && !photoSkus.has(topGap.sku));
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
    setPhoneError(null);
    try {
      await execution({
        play_id: play.play_id,
        node_id: nodeId,
        steps_done: steps.filter((s) => stepsDone[s.id]).map((s) => s.id),
      });
      setExecutionSaved(true);
    } catch (e) {
      setPhoneError({ error: toApiError(e, "/execution"), retry: markDone });
    }
  }

  const allConfirmable =
    rows?.every((r, i) => {
      if (r.needs_confirmation && confirmed[i] === undefined) return false;
      // A row confirmed "yes" but with no printed date can only commit once the operator
      // fills one in by hand -- that is the whole point of the confirmation flow.
      if (confirmed[i] === true && !r.best_before_date && !dateOverrides[i]) return false;
      return true;
    }) ?? false;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <h1>Priya&apos;s phone</h1>
      <p className="muted phone-intro">
        Capture to gap: photograph a pallet, confirm what Taal read, and see the gap it finds.
      </p>

      <div className="phone-frame">
      <section className="card">
        <label>
          Node{" "}
          <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
            {NODES.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <h3>Use a sample pallet photo</h3>
        <div className="photo-choices">
          {SAMPLE_PHOTOS.map((p) => (
            <button
              key={p.ref}
              type="button"
              className="photo-choice"
              aria-pressed={selectedPhoto === p.ref}
              onClick={() => pickSample(p.ref, p.src)}
            >
              <span className="photo-choice__frame">
                <Skeleton width="100%" height="100%" className="photo-choice__skeleton" />
                <Image src={p.src} alt={p.label} width={92} height={92} className="photo-choice__thumb" />
              </span>
              <span className="photo-choice__label">{p.label}</span>
            </button>
          ))}
        </div>

        <p className="muted">Own photo (experimental)</p>
        <label className="camera-button">
          <span className="camera-button__icon">
            <Icon name="camera" size={20} />
          </span>
          <span>Take or choose a photo</span>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={onOwnFile}
            aria-label="Own photo (experimental)"
          />
        </label>
        {ownFileName ? <p className="muted">Selected: {ownFileName}</p> : null}

        <div className="mic-row">
          <button
            type="button"
            className="mic-button"
            disabled
            title="Voice is not part of this demo"
            aria-label="Voice input (not available)"
            aria-describedby="mic-note"
          >
            <Icon name="mic" size={20} />
          </button>
          <span id="mic-note" className="muted">
            Voice is not part of this demo
          </span>
        </div>

        {previewSrc ? (
          <div
            ref={resultRef}
            tabIndex={-1}
            role="region"
            aria-label="Photo result"
            className="phone-result"
            data-testid="phone-result"
          >
            <div className="captured-photo">
              {/* eslint-disable-next-line @next/next/no-img-element -- an uploaded own-photo is a
                  blob/data URL, which next/image cannot optimise; a plain img handles both cases */}
              <img src={previewSrc} alt="Photographed pallet" />
              {capturing ? <span className="captured-photo__badge">Reading pallet…</span> : null}
              <button type="button" className="captured-photo__clear" onClick={clearPhoto}>
                Clear photo
              </button>
            </div>

            {rows ? (
              <>
                <table className="intake-table" data-testid="intake-table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Best before</th>
                      <th>Packs</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => (
                      <Fragment key={`frag-${i}`}>
                        <tr key={`row-${i}`}>
                          <td>
                            <span className="sku-name">{label("sku", row.sku_guess)}</span>
                            <Details inline summary="id">{row.sku_guess}</Details>
                          </td>
                          <td title={row.best_before_date ?? undefined}>{row.best_before_date ? (relativeDate(row.best_before_date, serverNow ?? undefined)?.short ?? row.best_before_date) : "–"}</td>
                          <td>{row.facings_count}</td>
                          <td>
                            <Confidence name="sku" value={row.sku_confidence} />
                            <Confidence name="date" value={row.date_confidence} />
                            <Confidence name="count" value={row.count_confidence} />
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
                              {confirmed[i] === true && !row.best_before_date ? (
                                <p>
                                  <label htmlFor={`date-${i}`}>Best-before date could not be read. Enter it: </label>
                                  <input
                                    id={`date-${i}`}
                                    type="date"
                                    value={dateOverrides[i] ?? ""}
                                    onChange={(e) => setDateOverrides((d) => ({ ...d, [i]: e.target.value }))}
                                  />
                                </p>
                              ) : null}
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
                <button type="button" className="button-primary" onClick={loadGapForNode} disabled={!allConfirmable || confirming}>
                  {confirming ? "Confirming…" : "Confirm rows"}
                </button>
                {confirmWritten !== null ? (
                  <p className="muted">
                    Wrote {confirmWritten} batch{confirmWritten === 1 ? "" : "es"}.
                    {confirmSkipped.length
                      ? ` Skipped ${confirmSkipped.length}: ${confirmSkipped
                          .map((s) => `${s.sku_guess} (${s.reason})`)
                          .join(", ")}.`
                      : ""}
                  </p>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
      </section>

      {phoneError ? (
        <ErrorCard error={phoneError.error} compact onRetry={phoneError.retry} />
      ) : null}

      {gap ? (
        <section ref={gapSectionRef}>
          {gapIsFallback ? (
            <p className="muted phone-fallback" role="status">
              <span className="chip phone-fallback__chip">Fallback gap</span>
              <span data-testid="gap-fallback-note">
                None of the photographed items raised a gap. Showing the node&apos;s biggest open gap instead.
              </span>
            </p>
          ) : null}
          {play ? (
            <PlayCard play={play} gap={gap} mode="hero" now={serverNow} onApproved={setApproveResult} />
          ) : (
            <GapCard gap={gap} now={serverNow} />
          )}
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
      </div>
    </main>
  );
}
