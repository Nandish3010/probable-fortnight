"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "../../components/Badge";
import { ErrorCard } from "../../components/ErrorCard";
import { Icon } from "../../components/icons";
import { InboxRow } from "../../components/InboxRow";
import { LiveReplan } from "../../components/LiveReplan";
import { ModelChip } from "../../components/ModelChip";
import { PlayCard } from "../../components/PlayCard";
import { PolicyEditor } from "../../components/PolicyEditor";
import { SourceBadge } from "../../components/SourceBadge";
import { TracePanel } from "../../components/TracePanel";
import { getGaps, getPlays, getPolicy, rerun } from "../../lib/api";
import { toApiError, type ApiError } from "../../lib/apiError";
import { pct } from "../../lib/format";
import { collapseRuns, inboxHeading } from "../../lib/inbox";
import { label } from "../../lib/labels";
import { recordPlan } from "../../lib/progressStore";
import { recordedGaps, recordedPlays } from "../../lib/recorded";
import { isPhoneNow } from "../../lib/useMediaQuery";
import { useServerNow } from "../../lib/useServerNow";
import { TraceView } from "../../components/traceRows";
import type { ApproveResponse, Gap, Play, RerunAccepted, RerunResult, TraceEvent } from "../../lib/types";

const PLAY_HASH = /^#play=(.+)$/;

function playIdFromHash(): string | null {
  if (typeof window === "undefined") return null;
  const m = PLAY_HASH.exec(window.location.hash);
  if (!m) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return null;
  }
}

function runIdFromTraceRef(traceRef: string): string {
  return traceRef.startsWith("events/") ? traceRef.slice("events/".length) : traceRef;
}

export default function PlayDeskPage() {
  const serverNow = useServerNow();
  const [plays, setPlays] = useState<Play[]>([]);
  const [gapsById, setGapsById] = useState<Record<string, Gap>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");
  const [holdoutFraction, setHoldoutFraction] = useState(0.1);
  const [language, setLanguage] = useState<string>("en");
  // A run is in flight exactly while rerunAccepted is set (cleared the moment its LiveReplan
  // calls onDone, at the same time rerunResult is set) -- the two are otherwise mutually exclusive.
  const [rerunAccepted, setRerunAccepted] = useState<RerunAccepted | null>(null);
  const [rerunResult, setRerunResult] = useState<RerunResult | null>(null);
  // The finished run's streamed trace, kept visible under the result (LiveReplan unmounts on done).
  const [liveTrace, setLiveTrace] = useState<TraceEvent[] | null>(null);

  const [planStarting, setPlanStarting] = useState(false);
  const [planError, setPlanError] = useState<ApiError | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [usingRecorded, setUsingRecorded] = useState(false);
  // Under 768px the Desk is two screens, the inbox and one play's detail ("Back to inbox" returns).
  // The screen lives in the URL hash (#play=<id>) so the browser's Back button does the same.
  const [screen, setScreen] = useState<"inbox" | "detail">("inbox");
  const inboxScroll = useRef(0);
  // True when this page itself added the "#play=" history entry (a tap on a row), so Back can undo it;
  // false when the page was opened on such a link, where Back would leave the page.
  const pushedHash = useRef(false);
  // Where keyboard focus goes after a phone changes screen. The control that was pressed unmounts
  // with its screen, which would leave focus on <body>.
  const focusAfterScreen = useRef<"detail" | "inbox" | null>(null);
  const [totalGaps, setTotalGaps] = useState<number | null>(null);
  // Plays approved from this page. Approval fixes the holdout (the assignment is already drawn),
  // so the slider locks for them; a play the API already reports as approved is locked too.
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set());
  // The fraction the server actually drew for each play approved here (read when the selection changes).
  const approvedFractions = useRef<Record<string, number>>({});

  // "Plan live": the same async run the policy editor starts (POST /rerun, streamed over SSE),
  // under the policy as it stands -- the planner runs for real on this gap and its tool calls and
  // guardrail checks stream into the trace below. The recorded run stays the default view.
  async function handlePlanLive(gapId: string) {
    setPlanStarting(true);
    setPlanError(null);
    try {
      const policy = await getPolicy();
      handleReplanStart(await rerun({ gap_id: gapId, policy_text: policy.text }));
    } catch (e) {
      setPlanError(toApiError(e, "/rerun"));
    } finally {
      setPlanStarting(false);
    }
  }

  // bumped on every accepted run so the policy editor re-reads the current version (a run under
  // changed text creates one; a live run under unchanged text does not)
  const [policyRefresh, setPolicyRefresh] = useState(0);

  function handleReplanStart(accepted: RerunAccepted) {
    setPolicyRefresh((n) => n + 1);
    setRerunResult(null);
    setLiveTrace(null);
    setRerunAccepted(accepted);
  }

  // Plays a run on this page produced, shown in the inbox under the recorded one (same gap, so the
  // same rupees at stake and a stable sort keeps them after it). The selection is left where it
  // is: the recorded play stays selected, and Approve acts on whichever play is selected.
  const [livePlayIds, setLivePlayIds] = useState<Set<string>>(new Set());

  function handleReplanDone(result: RerunResult, records: TraceEvent[]) {
    setRerunAccepted(null);
    setRerunResult(result);
    setLiveTrace([...records]);
    const livePlay = result.play;
    if (livePlay) {
      setPlays((prev) => [...prev.filter((p) => p.play_id !== livePlay.play_id), livePlay]);
      setLivePlayIds((prev) => new Set(prev).add(livePlay.play_id));
    }
  }

  function applyLoaded(playList: Play[], gapList: Gap[]) {
    setPlays(playList);
    const byId: Record<string, Gap> = {};
    gapList.forEach((g) => {
      byId[g.gap_id] = g;
    });
    setGapsById(byId);
    setTotalGaps(gapList.length);
    // A phone opened on #play=<id> (a shared link, a reload) lands on that play's detail screen.
    const wanted = playIdFromHash();
    const fromHash = wanted ? playList.find((p) => p.play_id === wanted) : undefined;
    if (fromHash && isPhoneNow()) {
      setSelectedId(fromHash.play_id);
      setScreen("detail");
    } else if (playList.length > 0) {
      setSelectedId(playList[0].play_id);
    }
  }

  // Only the most recent load may write state: a Retry (or React's dev-only second effect run)
  // must not be overwritten by an older request that settles later.
  const loadSeq = useRef(0);

  async function loadPlays() {
    const seq = ++loadSeq.current;
    setLoading(true);
    setLoadError(null);
    setUsingRecorded(false);
    try {
      const [playList, gapList] = await Promise.all([getPlays(), getGaps()]);
      if (seq !== loadSeq.current) return;
      applyLoaded(playList, gapList);
    } catch (e) {
      if (seq !== loadSeq.current) return;
      setLoadError(toApiError(e, "/plays"));
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }

  async function showRecordedPlays() {
    const [playList, gapList] = await Promise.all([recordedPlays(), recordedGaps()]);
    applyLoaded(playList, gapList);
    setLoadError(null);
    setUsingRecorded(true);
  }

  useEffect(() => {
    loadPlays();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleApproved(playId: string, res: ApproveResponse) {
    setApprovedIds((prev) => new Set(prev).add(playId));
    if (typeof res.assignment.fraction === "number") {
      approvedFractions.current[playId] = res.assignment.fraction;
      setHoldoutFraction(res.assignment.fraction);
    }
  }

  // One row per gap, ranked by rupees at stake; repeated runs of a gap collapse into the newest.
  const groups = useMemo(() => collapseRuns(plays, gapsById, livePlayIds), [plays, gapsById, livePlayIds]);

  function openPlay(id: string) {
    setSelectedId(id);
    if (!isPhoneNow()) return;
    inboxScroll.current = window.scrollY;
    pushedHash.current = true;
    window.location.hash = `play=${encodeURIComponent(id)}`; // a new history entry: Back returns to the inbox
    focusAfterScreen.current = "detail";
    setScreen("detail");
    window.scrollTo(0, 0);
  }

  function backToInbox() {
    if (pushedHash.current && playIdFromHash()) {
      window.history.back(); // the hashchange listener below shows the inbox
      return;
    }
    // Opened on a #play= link: there is no earlier entry of ours to go back to, so drop the hash.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    focusAfterScreen.current = "inbox";
    setScreen("inbox");
  }

  // The browser's Back and Forward (and a hand-edited hash) move between the two screens.
  useEffect(() => {
    function onHashChange() {
      const id = playIdFromHash();
      if (id && isPhoneNow()) {
        setSelectedId(id);
        focusAfterScreen.current = "detail";
        setScreen("detail");
        window.scrollTo(0, 0);
      } else {
        focusAfterScreen.current = "inbox";
        setScreen("inbox");
        const y = inboxScroll.current;
        requestAnimationFrame(() => window.scrollTo(0, y));
      }
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const selected = plays.find((p) => p.play_id === selectedId) ?? null;

  // Focus follows a phone's screen change: the play card's title on the detail screen, the row that
  // was open on the inbox screen.
  useEffect(() => {
    const target = focusAfterScreen.current;
    if (!target) return;
    const id = requestAnimationFrame(() => {
      if (focusAfterScreen.current !== target) return;
      focusAfterScreen.current = null;
      const el =
        target === "detail"
          ? document.querySelector<HTMLElement>('[data-testid="play-detail"] [data-card-title]')
          : document.querySelector<HTMLElement>('.inbox__item[aria-current="true"]');
      el?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(id);
  }, [screen, selectedId]);

  useEffect(() => {
    if (selected) {
      recordPlan(); // Arjun has a plan open: the stepper's Plan step
      setRationale(selected.rationale);
      setHoldoutFraction(approvedFractions.current[selected.play_id] ?? selected.holdout.fraction);
      setLanguage(selected.copy.language_set[0] ?? "en");
      setRerunAccepted(null);
      setRerunResult(null);
      setLiveTrace(null);
      setPlanError(null);
    }
  }, [selected]);

  const gap = selected ? gapsById[selected.gap_id] : undefined;
  const approved = selected ? selected.status === "approved" || approvedIds.has(selected.play_id) : false;

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <h1>Play Desk</h1>
      {loadError ? (
        <ErrorCard error={loadError} onRetry={loadPlays} onShowRecorded={showRecordedPlays} />
      ) : null}
      {usingRecorded ? (
        <p className="muted" data-testid="recorded-note">
          <Badge kind="replay" detail="recorded copy" /> The live service is not answering, so these are the recorded
          plays that ship with the app.
        </p>
      ) : null}
      <div className="desk-layout" data-screen={screen} data-testid="desk-layout">
        <div className="inbox-pane" data-testid="inbox-pane">
          <h2 className="inbox__title" data-testid="inbox-heading">
            {inboxHeading(groups.length, totalGaps)}
          </h2>
          <div className="inbox" aria-label="Play inbox">
            {groups.map((group) => (
              <InboxRow
                key={group.gapId}
                group={group}
                gap={gapsById[group.gapId]}
                now={serverNow}
                selectedId={selectedId}
                liveIds={livePlayIds}
                onSelect={openPlay}
              />
            ))}
            {groups.length === 0 && loading ? <p className="muted">Loading plays…</p> : null}
            {groups.length === 0 && !loading && !loadError ? <p className="muted">No plays yet.</p> : null}
          </div>
        </div>

        <div className="desk-detail">
          <div className="desk-back" data-testid="desk-back">
            <button type="button" className="desk-back__button" onClick={backToInbox}>
              <Icon name="chevron-left" size={20} />
              Back to inbox
            </button>
          </div>
          {!selected ? (
            <p className="muted">Select a play.</p>
          ) : (
            <div data-testid="play-detail">
              {/* keyed by play: switching plays starts a fresh Approve, never the last play's result */}
              <PlayCard
                key={selected.play_id}
                play={selected}
                gap={gap}
                mode="detail"
                now={serverNow}
                holdoutFraction={holdoutFraction}
                rationale={rationale}
                onApproved={(res) => handleApproved(selected.play_id, res)}
                badges={
                  <span className="chip" data-testid="play-status">
                    {selected.status}
                  </span>
                }
                decisionExtra={
                  <div className="holdout-control">
                    <label htmlFor="holdout-range">Holdout fraction</label>
                    <input
                      id="holdout-range"
                      type="range"
                      min={0.05}
                      max={0.5}
                      step={0.01}
                      value={holdoutFraction}
                      onChange={(e) => setHoldoutFraction(Number(e.target.value))}
                      disabled={approved}
                    />
                    <span className="num"> {pct(holdoutFraction, 0)}</span>
                    {approved ? (
                      <p className="muted" data-testid="holdout-locked">
                        Locked: this play is approved, so its holdout group is already drawn.
                      </p>
                    ) : null}
                  </div>
                }
                whyThisPlay={
                  <div className="rationale-section">
                    <p className="rationale-section__subtitle">
                      Every number here is cited back to the gap, the estimator, the policy and the forecast &mdash;
                      the planner cannot state a figure it cannot resolve. Edits are saved with the approval.
                    </p>
                    <textarea
                      className="rationale-section__textarea"
                      value={rationale}
                      onChange={(e) => setRationale(e.target.value)}
                      rows={7}
                      aria-label="Rationale"
                    />
                  </div>
                }
              >
                <section className="play-card__section">
                  <h4>Copy</h4>
                  <div className="lang-toggle" role="group" aria-label="Language">
                    {selected.copy.language_set.map((lang) => (
                      <button
                        key={lang}
                        type="button"
                        aria-pressed={language === lang}
                        onClick={() => setLanguage(lang)}
                      >
                        {lang.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  {selected.copy.variants
                    .filter((v) => v.language === language)
                    .map((v) => (
                      <p key={`${v.segment_id}-${v.language}`}>{v.text}</p>
                    ))}
                </section>

                <section className="play-card__section">
                  <div className="trace-section__head">
                    <h4>Trace</h4>
                    <button
                      type="button"
                      onClick={() => handlePlanLive(selected.gap_id)}
                      disabled={planStarting || rerunAccepted !== null}
                      data-testid="plan-live"
                    >
                      {planStarting || rerunAccepted ? "Planning live…" : "Plan live"}
                    </button>
                  </div>
                  <p className="muted trace-section__hint">
                    The trace below is the recorded run. <strong>Plan live</strong> runs the planner on this gap now and
                    streams each tool call and guardrail check as it happens, with the time elapsed.
                  </p>
                  {planError ? (
                    <ErrorCard
                      error={planError}
                      compact
                      onRetry={() => handlePlanLive(selected.gap_id)}
                      title={planError.kind === "conflict" ? "A re-plan is already running" : undefined}
                      body={planError.kind === "conflict" ? "Wait for it to finish, then try again." : undefined}
                    />
                  ) : null}
                  <TracePanel runId={runIdFromTraceRef(selected.trace_ref)} />
                  {rerunAccepted ? (
                    <div className="trace-section__live">
                      <h5>Live run</h5>
                      <LiveReplan accepted={rerunAccepted} onDone={handleReplanDone} />
                    </div>
                  ) : null}
                </section>

                <section className="play-card__section">
                  <h4>Policy</h4>
                  <PolicyEditor gapId={selected.gap_id} onReplanStart={handleReplanStart} replanning={rerunAccepted !== null || planStarting} refreshKey={policyRefresh} />
                </section>

                {rerunResult ? (
                  <section className="play-card__section" role="status" aria-live="polite">
                    <h4>Re-plan result</h4>
                    <div className="drawer">
                      {rerunResult.status === "error" ? (
                        <p className="error">Re-plan failed: {rerunResult.error || "unknown error"}</p>
                      ) : rerunResult.status === "no_play" || !rerunResult.play ? (
                        <>
                          <p>
                            The planner could not produce a valid play this time
                            {rerunResult.fallback_reason ? ` (${rerunResult.fallback_reason})` : ""}.
                          </p>
                          <p>
                            <SourceBadge source={rerunResult.source} fallbackReason={rerunResult.fallback_reason} />
                          </p>
                        </>
                      ) : (
                        <>
                          <p>
                            <strong>Old:</strong> {selected.mechanic} — {selected.rationale}
                          </p>
                          <p>
                            <strong>New ({rerunResult.policy_version}):</strong> {rerunResult.play.mechanic} — {rerunResult.play.rationale}
                          </p>
                          <p className="re-plan-result__meta">
                            <SourceBadge source={rerunResult.source} fallbackReason={rerunResult.fallback_reason} />
                            {typeof rerunResult.iterations === "number" ? (
                              <span className="muted"> {rerunResult.iterations} iteration{rerunResult.iterations === 1 ? "" : "s"}</span>
                            ) : null}
                            {" "}
                            <ModelChip latencyMs={rerunResult.elapsed_ms} plainTimeWithoutModel />
                          </p>
                        </>
                      )}
                    </div>
                  </section>
                ) : null}

                {liveTrace && liveTrace.length > 0 ? (
                  <section className="play-card__section" data-testid="live-trace">
                    <details open>
                      <summary>
                        <strong>Live run trace</strong> <span className="muted">· {liveTrace.length} events</span>
                      </summary>
                      <TraceView events={liveTrace} label="Finished live run trace" />
                    </details>
                  </section>
                ) : null}
              </PlayCard>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
