// "Show recorded result": the copy of a screen's data that ships with the app, offered next to
// Retry when the live service does not answer (components/ErrorCard.tsx). These are the same
// fixtures mock mode serves (web/mocks), so what a visitor sees is always labelled REPLAY and
// never presented as a live read.
//
// They are dynamic imports on purpose: a visitor whose service is healthy never downloads them,
// and they stay out of the first-load JavaScript of every route. (Mock mode itself loads its
// fixtures through lib/mockData.ts, which a production build drops entirely.)
import type { EventsResponse, Gap, Outcome, Play } from "./types";

export async function recordedGaps(): Promise<Gap[]> {
  const gaps = (await import("../mocks/gaps.json")).default as unknown as Gap[];
  return [...gaps].sort((a, b) => b.rupees_at_stake - a.rupees_at_stake);
}

export async function recordedPlays(gapId?: string): Promise<Play[]> {
  const plays = (await import("../mocks/plays.json")).default as unknown as Play[];
  return gapId ? plays.filter((p) => p.gap_id === gapId) : plays;
}

export async function recordedEvents(): Promise<EventsResponse> {
  return (await import("../mocks/events.json")).default as unknown as EventsResponse;
}

export async function recordedOutcomes(): Promise<Outcome[]> {
  return (await import("../mocks/outcomes.json")).default as unknown as Outcome[];
}
