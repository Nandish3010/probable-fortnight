// Script detection for customer replies. The chat agent sometimes answers a Kannada-preference
// customer in English (a model fallback); the UI says so instead of presenting it as Kannada.
// Pure, no React: tests/e2e/lang.spec.ts runs it in node.

const KANNADA = /[ಀ-೿]/;

/** True when the text holds at least one Kannada letter, digit or sign (U+0C80 to U+0CFF). Any
 * Kannada counts as Kannada: a reply that mixes Kannada with an English product name is Kannada. */
export function containsKannada(text: string | null | undefined): boolean {
  return typeof text === "string" && KANNADA.test(text);
}

export type ReplyLanguage = "kannada" | "english" | "english_fallback";

/** Which language a reply is in, judged from its script, not from the `language` field the API
 * sends (the mock fixtures tag English text "kn"). `customerLanguage` is the customer's preferred
 * language ("kn", "en"): an English reply to a Kannada customer is an "english_fallback". */
export function replyLanguage(text: string | null | undefined, customerLanguage?: string | null): ReplyLanguage {
  if (containsKannada(text)) return "kannada";
  return (customerLanguage ?? "").toLowerCase().startsWith("kn") ? "english_fallback" : "english";
}

/** The lang attribute for a reply's own text. */
export function langAttr(language: ReplyLanguage): "kn" | "en" {
  return language === "kannada" ? "kn" : "en";
}

const LANGUAGE_NAMES: Record<string, string> = {
  kn: "Kannada",
  en: "English",
  hi: "Hindi",
  ta: "Tamil",
  te: "Telugu",
  ml: "Malayalam",
  mr: "Marathi",
  bn: "Bengali",
};

/** "kn" -> "Kannada", "en-IN" -> "English". An unknown code is returned as given, so a new
 * language shows its code instead of a blank. */
export function languageName(code: string | null | undefined): string {
  if (!code) return "Unknown language";
  const base = code.toLowerCase().split(/[-_]/)[0];
  return LANGUAGE_NAMES[base] ?? code;
}

/** Quick-reply buttons with equal labels collapsed to the first one (the backend sometimes sends
 * the same label twice with different ids). Case and surrounding space are ignored. */
export function uniqueByLabel<T extends { label: string }>(items: readonly T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const key = item.label.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}
