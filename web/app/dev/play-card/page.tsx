"use client";

// A preview of the decision card in its three modes, from the recorded fixtures. Mock mode only
// (NEXT_PUBLIC_TAAL_MOCK=1, the Playwright and local-demo build); any other build answers 404. It
// exists because the feed mode has no route of its own yet, and so the modes can be looked at and
// tested side by side.
import { notFound } from "next/navigation";
import { useEffect, useState } from "react";
import { PlayCard, type PlayCardMode } from "../../../components/PlayCard";
import { recordedGaps, recordedPlays } from "../../../lib/recorded";
import { useServerNow } from "../../../lib/useServerNow";
import type { Gap, Play } from "../../../lib/types";

const MODES: PlayCardMode[] = ["hero", "detail", "feed"];

export default function PlayCardPreview() {
  if (process.env.NEXT_PUBLIC_TAAL_MOCK !== "1") notFound();
  const now = useServerNow();
  const [data, setData] = useState<{ play: Play; gap: Gap } | null>(null);

  useEffect(() => {
    Promise.all([recordedPlays(), recordedGaps()]).then(([plays, gaps]) => {
      const play = plays[0];
      const gap = gaps.find((g) => g.gap_id === play?.gap_id);
      if (play && gap) setData({ play, gap });
    });
  }, []);

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <h1>Decision card: three modes</h1>
      {data
        ? MODES.map((mode) => (
            <section key={mode} aria-label={`${mode} mode`} data-testid={`preview-${mode}`}>
              <h2>{mode}</h2>
              <PlayCard play={data.play} gap={data.gap} mode={mode} now={now} testId={`play-card-${mode}`} />
            </section>
          ))
        : <p className="muted">Loading the recorded play…</p>}
    </main>
  );
}
