import type { BadgeKind } from "../components/Badge";

/** What the chip beside the phone view's result table says about where the read came from. */
export interface VisionProvenance {
  kind: BadgeKind;
  detail: string;
  /** One sentence for the badge's tooltip. */
  title: string;
  /** Which of the three it is, for the page and its tests. */
  source: "replay" | "live" | "scripted";
}

// agents/capture/vision.py: a staged sample pallet is answered from its recorded Gemini read and
// carries model_id "recorded" (only a real upload is read live, and then model_id is the Gemini
// model that answered); the stub backend answers "stub-vision".
const RECORDED = "recorded";
const STUB = "stub-vision";

/**
 * The provenance chip for one /capture response. The API's own `model_id` decides what a response
 * is; a sample tile (sent as a photo_ref, never as image data) can only ever be a replay, so it is
 * labelled one even when the backend is the stub. A live chip needs a real model id in the response:
 * an upload with no usable model_id gets no chip at all rather than an assumed one.
 */
export function visionProvenance(modelId: string | null | undefined, isSample: boolean): VisionProvenance | null {
  const id = (modelId ?? "").trim();
  if (id === RECORDED || (isSample && (id === STUB || id === ""))) {
    return {
      kind: "replay",
      detail: "sample photo (AI-generated) · recorded Gemini vision read",
      title: "This sample pallet photo is an AI-generated image. The read shown is a Gemini vision read recorded earlier and played back; nothing was read just now.",
      source: "replay",
    };
  }
  if (id === STUB) {
    return {
      kind: "scripted",
      detail: "your upload · stand-in vision, no Gemini call",
      title: "The server is running its scripted stand-in for the vision model, so this read did not come from Gemini.",
      source: "scripted",
    };
  }
  if (id === "") return null;
  return {
    kind: "live-gemini",
    detail: `your upload · ${id}`,
    title: "Your photo was read just now by the Gemini vision model.",
    source: "live",
  };
}
