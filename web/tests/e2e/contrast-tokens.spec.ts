import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

// Contrast sanity for the tokens that carry text, computed from app/globals.css itself: the
// light values from the first :root block, the dark values from the two dark blocks (which must
// agree with each other: a token with a dark value is declared in both places).

const css = fs.readFileSync(path.resolve(__dirname, "../../app/globals.css"), "utf-8");

function blockBody(start: string): string {
  const i = css.indexOf(start);
  if (i < 0) throw new Error(`block not found: ${start}`);
  const open = css.indexOf("{", i);
  let depth = 0;
  for (let j = open; j < css.length; j++) {
    if (css[j] === "{") depth++;
    if (css[j] === "}" && --depth === 0) return css.slice(open + 1, j);
  }
  throw new Error("unbalanced block");
}

function declarations(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

const light = declarations(blockBody(":root {"));
const darkMedia = declarations(blockBody(':root:not([data-theme="light"])'));
const darkAttr = declarations(blockBody(':root[data-theme="dark"]'));
const dark = { ...light, ...darkAttr };

function resolve(tokens: Record<string, string>, name: string): string {
  let v = tokens[name];
  for (let i = 0; i < 5 && v && v.startsWith("var("); i++) v = tokens[v.slice(4, -1).trim()];
  if (!v || !/^#[0-9a-f]{6}$/i.test(v)) throw new Error(`${name} does not resolve to a hex colour: ${v}`);
  return v;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const MIN = 4.5;

test.describe("contrast tokens (>= 4.5:1)", () => {
  test("the contrast function is right (white on black is 21:1, white on white is 1:1)", () => {
    expect(contrast("#ffffff", "#000000")).toBeCloseTo(21, 5);
    expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  });

  for (const [theme, tokens] of [["light", light], ["dark", dark]] as const) {
    for (const bg of ["--bg", "--surface", "--surface-alt"]) {
      test(`${theme}: --good-text on ${bg}`, () => {
        const r = contrast(resolve(tokens, "--good-text"), resolve(tokens, bg));
        expect(r, `${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(MIN);
      });
      test(`${theme}: --text-muted on ${bg}`, () => {
        const r = contrast(resolve(tokens, "--text-muted"), resolve(tokens, bg));
        expect(r, `${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(MIN);
      });
      test(`${theme}: --danger-text on ${bg}`, () => {
        const r = contrast(resolve(tokens, "--danger-text"), resolve(tokens, bg));
        expect(r, `${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(MIN);
      });
    }
  }

  test("dark: --on-accent on the accent fill (white was about 3:1)", () => {
    const r = contrast(resolve(dark, "--on-accent"), resolve(dark, "--accent"));
    expect(r, `${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(MIN);
    // and the old choice really was worse, which is why the token exists
    expect(contrast("#ffffff", resolve(dark, "--accent"))).toBeLessThan(MIN);
  });

  test("light: --on-accent on the accent fill and its hover colour", () => {
    expect(contrast(resolve(light, "--on-accent"), resolve(light, "--accent"))).toBeGreaterThanOrEqual(MIN);
    expect(contrast(resolve(light, "--on-accent"), resolve(light, "--accent-strong"))).toBeGreaterThanOrEqual(MIN);
  });

  test("dark: --on-accent on the accent hover colour; destructive label on the danger fill, both themes", () => {
    expect(contrast(resolve(dark, "--on-accent"), resolve(dark, "--accent-strong"))).toBeGreaterThanOrEqual(MIN);
    expect(contrast(resolve(light, "--on-accent"), resolve(light, "--danger"))).toBeGreaterThanOrEqual(MIN);
    expect(contrast(resolve(dark, "--on-accent"), resolve(dark, "--danger"))).toBeGreaterThanOrEqual(MIN);
  });

  test("semantic -fg tokens read on the surface in both themes", () => {
    for (const [theme, tokens] of [["light", light], ["dark", dark]] as const) {
      for (const t of ["pass", "na", "pending", "fallback", "synthetic", "fail"]) {
        const r = contrast(resolve(tokens, `--state-${t}-fg`), resolve(tokens, "--surface"));
        expect(r, `${theme} --state-${t}-fg ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(MIN);
      }
    }
  });

  test("a token that differs between light and dark is declared in both dark blocks, with the same value", () => {
    for (const name of Object.keys(darkAttr)) {
      expect(darkMedia[name], `${name} is missing from the prefers-color-scheme block`).toBe(darkAttr[name]);
    }
    for (const name of Object.keys(darkMedia)) {
      expect(darkAttr[name], `${name} is missing from the [data-theme=dark] block`).toBe(darkMedia[name]);
    }
    for (const name of ["--on-accent", "--danger-text", "--text-muted", "--live-text"]) {
      expect(darkAttr[name], name).toBeTruthy();
    }
  });

  test("no gradient text, no orange hero glow, no gradient tokens remain", () => {
    expect(css).not.toMatch(/background-clip:\s*text/);
    expect(css).not.toMatch(/--gradient-/);
    expect(css).not.toMatch(/--bg-grad/);
    expect(css).not.toMatch(/radial-gradient/);
  });
});
