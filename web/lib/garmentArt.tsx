// A small, purely presentational garment-shape glyph, used only so a pairing row in the stylist
// chat reads as "a piece of clothing" rather than a bare colour dot. There is no product photo
// per SKU anywhere in this dataset (see docs/schemas/tools/stylist.suggest_pairings.schema.json);
// this draws a simple silhouette for the item's `garment_type`, tinted with the same hex the
// colour dot already used (colour.ts::swatchFor). It never decides a pairing, only illustrates
// one the server already picked.

/** Every stylist `garment_type` (data/generator/apparel.py::GARMENTS) mapped to one of a small
 * set of hand-drawn silhouette keys. Unlisted or unrecognised types fall back by role in
 * `iconKeyFor`. */
const GARMENT_TYPE_TO_ICON: Record<string, IconKey> = {
  kurta: "top", kurti: "top", "saree blouse": "top", "t-shirt": "top", shirt: "top",
  polo: "top", "crop top": "top", tunic: "top", sweatshirt: "top", hoodie: "top",
  palazzo: "bottom", salwar: "bottom", churidar: "bottom", "dhoti pants": "bottom",
  chinos: "bottom", jeans: "bottom", trousers: "bottom", shorts: "bottom", skirt: "bottom",
  leggings: "bottom",
  dress: "dress", anarkali: "dress", saree: "dress", "lehenga set": "dress",
  jumpsuit: "dress", sherwani: "dress", "kurta set": "dress",
  dupatta: "scarf", stole: "scarf", scarf: "scarf",
  jacket: "jacket", blazer: "jacket", cardigan: "jacket", "nehru jacket": "jacket",
  shrug: "jacket", sweater: "jacket",
  sneakers: "shoe", kolhapuris: "shoe", sandals: "shoe", loafers: "shoe",
  mojaris: "shoe", boots: "shoe", juttis: "shoe", heels: "heel",
  earrings: "earrings", necklace: "necklace", bangles: "bangles", watch: "watch",
  sunglasses: "sunglasses", belt: "belt", handbag: "bag", tote: "bag", clutch: "bag",
  cap: "cap", brooch: "brooch",
};

const ROLE_FALLBACK_ICON: Record<string, IconKey> = {
  top: "top", bottom: "bottom", dress: "dress", layer: "jacket", footwear: "shoe", accessory: "bag",
};

type IconKey =
  | "top" | "bottom" | "dress" | "jacket" | "scarf" | "shoe" | "heel"
  | "earrings" | "necklace" | "bangles" | "watch" | "sunglasses" | "belt" | "bag" | "cap" | "brooch";

export function iconKeyFor(garmentType: string | null | undefined, role?: string | null): IconKey | null {
  if (garmentType) {
    const key = GARMENT_TYPE_TO_ICON[garmentType.toLowerCase()];
    if (key) return key;
  }
  if (role) return ROLE_FALLBACK_ICON[role] ?? null;
  return null;
}

// Simple line-art paths, viewBox 0 0 24 24, stroke-based so the colour tint reads as fabric/metal
// rather than a filled blob.
const ICON_PATHS: Record<IconKey, string> = {
  top: "M8 3 4 6l1.5 3L8 7.5V20h8V7.5L18.5 9 20 6l-4-3-2 1.5h-4z",
  bottom: "M6 3h12l.6 8-1.6 10h-3l-.8-9-.8 9h-3L7.4 11z",
  dress: "M9 3h6l1 5 2 12H6l2-12z",
  jacket: "M8 3 4 6l1.5 3L8 7.5V20h8V7.5L18.5 9 20 6l-4-3-2 1.5h-4zM8 7v4M16 7v4",
  scarf: "M3 8c3 3 6-3 9 0s6-3 9 0M3 8v4c3 3 6-3 9 0s6-3 9 0v-4",
  shoe: "M4 15c0-3 2-6 4-7l2 2 3-1 2 2h3a3 3 0 0 1 3 3v2z M4 15h14",
  heel: "M5 12c2-4 4-6 6-7l2 2-1 2 3 1v3a3 3 0 0 1-3 3H6l3-3-2-3z",
  earrings: "M12 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM12 7v3a4 4 0 1 0 4 4",
  necklace: "M4 4c2 6 6 9 8 9s6-3 8-9 M12 13a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  bangles: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8a4 4 0 1 0 0 8",
  watch: "M9 3h6l.6 4h-7.2zM9 21h6l.6-4h-7.2z M7 7h10v10H7z",
  sunglasses: "M2 9h4l2 2h8l2-2h4 M6 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  belt: "M2 11h20v2H2z M9 8h6v8H9z",
  bag: "M6 8h12l1 12H5zM9 8V6a3 3 0 0 1 6 0v2",
  cap: "M3 14a9 6 0 0 1 18 0z M9 14v-3a3 3 0 0 1 6 0v3",
  brooch: "M12 4l2 4 4 1-3 3 1 4-4-2-4 2 1-4-3-3 4-1z",
};

/** Garment-shaped icon, tinted with `hex` (falls back to a neutral outline when hex is unknown).
 * Renders nothing if the garment_type/role can't be mapped to a shape, so callers should keep
 * their own dot fallback for that case. */
export function GarmentGlyph({
  garmentType,
  role,
  hex,
}: {
  garmentType?: string | null;
  role?: string | null;
  hex?: string | null;
}) {
  const key = iconKeyFor(garmentType, role);
  if (!key) return null;
  const stroke = hex ?? "currentColor";
  return (
    <svg
      className="chat-msg__glyph"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke={stroke}
      strokeWidth={1.6}
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d={ICON_PATHS[key]} />
    </svg>
  );
}
