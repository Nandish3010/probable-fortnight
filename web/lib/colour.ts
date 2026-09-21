// A small, purely presentational mirror of the colour word -> hue-family lookup in
// agents/stylist/colour.py, used only to show a swatch dot next to a pairing row title.
// The stylist's actual colour-wheel logic lives entirely server-side; this never decides
// a pairing, it only renders one already-decided pairing's colour visually.
const FAMILY_HEX: Record<string, string> = {
  red: "#c62828",
  "red-orange": "#d2691e",
  orange: "#e07a1a",
  "yellow-orange": "#c98a13",
  yellow: "#c9a227",
  "yellow-green": "#7a8c1f",
  green: "#2e7d32",
  "blue-green": "#00796b",
  blue: "#1565c0",
  "blue-violet": "#4a4ab8",
  violet: "#6a3fa0",
  "red-violet": "#a83279",
  white: "#f5f5f0",
  black: "#1a1a1a",
  grey: "#8a8a8a",
  beige: "#c9b28a",
  denim: "#3b5b7a",
  navy: "#1f2a4a",
};

const WORD_TO_FAMILY: Record<string, string> = {
  red: "red", crimson: "red", maroon: "red", wine: "red", burgundy: "red",
  rust: "red-orange", coral: "red-orange", peach: "red-orange", terracotta: "red-orange",
  orange: "orange", tangerine: "orange",
  mustard: "yellow-orange", amber: "yellow-orange", saffron: "yellow-orange",
  yellow: "yellow", gold: "yellow", golden: "yellow", lemon: "yellow",
  olive: "yellow-green", lime: "yellow-green", chartreuse: "yellow-green",
  green: "green", emerald: "green", mint: "green", sage: "green", jade: "green",
  teal: "blue-green", turquoise: "blue-green", seagreen: "blue-green",
  blue: "blue", cobalt: "blue", cerulean: "blue", royal: "blue",
  indigo: "blue-violet", periwinkle: "blue-violet",
  purple: "violet", violet: "violet", lavender: "violet", plum: "violet", lilac: "violet",
  magenta: "red-violet", pink: "red-violet", fuchsia: "red-violet", blush: "red-violet", rani: "red-violet",
  white: "white", cream: "white", ivory: "white",
  black: "black", charcoal: "grey", silver: "grey", grey: "grey", gray: "grey",
  beige: "beige", tan: "beige", khaki: "beige", camel: "beige", sand: "beige", nude: "beige",
  denim: "denim", chambray: "denim",
  navy: "navy",
};

/** First colour word found in a garment title/description, as a swatch hex -- or null if none matches. */
export function swatchFor(text: string): string | null {
  const words = text.toLowerCase().replace(/[^a-z\s-]/g, "").split(/\s+/);
  for (const w of words) {
    const family = WORD_TO_FAMILY[w];
    if (family) return FAMILY_HEX[family];
  }
  return null;
}
