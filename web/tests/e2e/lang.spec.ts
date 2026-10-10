import { test, expect } from "@playwright/test";
import { containsKannada, langAttr, replyLanguage } from "../../lib/lang";
import { describeReply, hasNoOffer } from "../../lib/previewReply";
import type { ChatEnvelope, DemoCustomer } from "../../lib/types";

// Script detection and the preview's reading of a reply. No browser: pure functions.

test.describe("lib/lang: Kannada script detection", () => {
  test("U+0C80 to U+0CFF is Kannada; the edges count, the neighbours do not", () => {
    expect(containsKannada("ಀ")).toBe(true);
    expect(containsKannada("೿")).toBe(true);
    expect(containsKannada("౿")).toBe(false); // last Telugu code point
    expect(containsKannada("ഀ")).toBe(false); // first Malayalam code point
  });

  test("any Kannada makes the text Kannada, even mixed with English words and rupees", () => {
    expect(containsKannada("Masala Chips 200G: ಇಂದು Coconut Water 1L ಜೊತೆ ₹61ಕ್ಕೆ")).toBe(true);
    expect(containsKannada("ಕಾರ್ಟ್‌ಗೆ ಸೇರಿಸಿ · Add to cart")).toBe(true);
  });

  test("English, digits, rupee signs, Devanagari and empty text are not Kannada", () => {
    expect(containsKannada("Here is what I found for \"chips\" at your store: ₹30")).toBe(false);
    expect(containsKannada("नमस्ते")).toBe(false);
    expect(containsKannada("")).toBe(false);
    expect(containsKannada(null)).toBe(false);
    expect(containsKannada(undefined)).toBe(false);
  });

  test("replyLanguage: Kannada text; English to an English customer; English to a Kannada customer is a fallback", () => {
    expect(replyLanguage("ಇಂದು ಆಫರ್", "kn")).toBe("kannada");
    expect(replyLanguage("ಇಂದು ಆಫರ್", "en")).toBe("kannada");
    expect(replyLanguage("No offers for you today.", "en")).toBe("english");
    expect(replyLanguage("No offers for you today.", "kn")).toBe("english_fallback");
    expect(replyLanguage("No offers for you today.", "KN")).toBe("english_fallback");
    expect(replyLanguage("No offers for you today.", "kn-IN")).toBe("english_fallback");
    expect(replyLanguage("No offers for you today.", undefined)).toBe("english");
    expect(replyLanguage("No offers for you today.", null)).toBe("english");
  });

  test("langAttr: kn only for Kannada text", () => {
    expect(langAttr("kannada")).toBe("kn");
    expect(langAttr("english")).toBe("en");
    expect(langAttr("english_fallback")).toBe("en");
  });
});

const env = (over: Partial<ChatEnvelope>): ChatEnvelope => ({ session_id: "CUST-MEENA:web", role: "agent", text: "x", ...over });
const cust = (over: Partial<DemoCustomer>): DemoCustomer => ({
  customer_id: "CUST-MEENA",
  display_name: "Meena",
  home_node_id: "DS-07",
  language: "kn",
  role: "sample",
  note: "",
  ...over,
});

test.describe("lib/previewReply", () => {
  test("a reply that carries a play is on offer; one with no play citation is not", () => {
    expect(hasNoOffer(env({ citations: [{ type: "play", ref: "play_x" }] }))).toBe(false);
    expect(hasNoOffer(env({ citations: [{ type: "stock", ref: "SKU@DS-07" }] }))).toBe(true);
    expect(hasNoOffer(env({}))).toBe(true);
  });

  test("Kannada reply to a treated Kannada customer: Kannada, in the audience", () => {
    const r = describeReply(env({ text: "ಇಂದು ಆಫರ್", citations: [{ type: "play", ref: "play_x" }] }), cust({}));
    expect(r).toEqual({ language: "kannada", offAudience: false });
  });

  test("English reply to a Kannada customer is labelled an English fallback", () => {
    const r = describeReply(env({ text: "Hello Meena! No offers for you today.", citations: [{ type: "play", ref: "play_x" }] }), cust({}));
    expect(r.language).toBe("english_fallback");
  });

  test("the language falls back to the envelope's own field when the customer record is not available", () => {
    expect(describeReply(env({ text: "Hello", language: "kn" }), null).language).toBe("english_fallback");
    expect(describeReply(env({ text: "Hello", language: "en" }), null).language).toBe("english");
  });

  test("a holdout customer, or a reply with no offer, gets the audience caption", () => {
    expect(describeReply(env({ text: "ಇಂದು", citations: [{ type: "play", ref: "p" }] }), cust({ role: "holdout" })).offAudience).toBe(true);
    expect(describeReply(env({ text: "I don't have any offers for you right now." }), cust({})).offAudience).toBe(true);
  });
});

test.describe("lib/lang: names and duplicates", () => {
  test("languageName gives the plain name and falls back to the code", async () => {
    const { languageName } = await import("../../lib/lang");
    expect(languageName("kn")).toBe("Kannada");
    expect(languageName("EN-IN")).toBe("English");
    expect(languageName("xx")).toBe("xx");
    expect(languageName(undefined)).toBe("Unknown language");
  });

  test("uniqueByLabel keeps the first of equal labels and leaves the order alone", async () => {
    const { uniqueByLabel } = await import("../../lib/lang");
    const out = uniqueByLabel([
      { id: "a", label: "Add to cart" },
      { id: "b", label: "Not now" },
      { id: "c", label: " add to cart " },
      { id: "d", label: "STOP" },
    ]);
    expect(out.map((b) => b.id)).toEqual(["a", "b", "d"]);
  });
});
