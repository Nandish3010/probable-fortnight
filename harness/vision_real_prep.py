"""Privacy pass for real phone photos before any of them go near git.

    uv run python -m harness.vision_real_prep --src .local/photos --out eval/raw/vision_real_2026-09-2X
    uv run python -m harness.vision_real_prep --src .local/photos --out ... --exclude IMG_0412.jpg

Reads `<src>/labels.csv` (file, product_name, best_before_date, units_visible, mrp_inr), and for
every listed photo that is not excluded:

1. applies the EXIF orientation to the pixels (so dropping EXIF does not rotate the photo),
2. re-encodes to RGB JPEG with no EXIF, ICC, XMP or comment block (GPS, device, timestamps go),
3. downscales so the longest side is <= 1280 px and lowers JPEG quality until the file is <= 300 KB,
4. renames it `photo_NN.jpg` -- phone filenames (IMG_20260925_181204.jpg) carry a timestamp too.

Then it re-opens every written file and fails (exit 1, nothing reported as clean) if any EXIF /
XMP / ICC / comment marker survives or a size limit is broken. `labels.json` is written next to
the photos with the new names; the original-name -> new-name map stays in `<src>/name_map.json`
(under .local/, gitignored) and is never committed.

Faces, name badges and store logos cannot be detected reliably by a script: a person looks at
each photo and passes `--exclude` for any that show one. Excluded files are listed (by original
name only, never described) in `<src>/excluded.json` so the owner can be told.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

MAX_SIDE = 1280
MAX_BYTES = 300 * 1024
LABEL_FIELDS = ("file", "product_name", "best_before_date", "units_visible", "mrp_inr")
# Byte markers of the metadata blocks a JPEG can carry. Any of them in an output file is a fail.
FORBIDDEN_MARKERS = {
    "exif": b"Exif\x00\x00",
    "xmp": b"http://ns.adobe.com/xap/",
    "icc": b"ICC_PROFILE",
    "photoshop_iptc": b"Photoshop 3.0",
}


def read_labels(path: Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in LABEL_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}; need {list(LABEL_FIELDS)}")
        rows = []
        for i, r in enumerate(reader, start=2):
            file = (r["file"] or "").strip()
            if not file:
                continue
            try:
                bb = date.fromisoformat(r["best_before_date"].strip()).isoformat()
                units = int(r["units_visible"])
                mrp = float(r["mrp_inr"]) if (r["mrp_inr"] or "").strip() else None
            except ValueError as e:
                raise ValueError(f"{path}:{i}: {e}") from e
            rows.append({"file": file, "product_name": r["product_name"].strip(), "best_before_date": bb, "units_visible": units, "mrp_inr": mrp})
    return rows


def clean_jpeg(src: Path) -> bytes:
    """Pixels only: orientation applied, RGB, longest side <= MAX_SIDE, no metadata, <= MAX_BYTES."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        # A fresh image from raw pixel data carries no info dict at all, so nothing can leak
        # through im.info (Pillow re-attaches info["exif"] / ["icc_profile"] on save otherwise).
        bare = Image.frombytes("RGB", im.size, im.tobytes())
    for quality in (88, 84, 80, 75, 70, 65, 60, 55, 50):
        buf = io.BytesIO()
        bare.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    raise ValueError(f"{src.name}: cannot reach {MAX_BYTES} bytes at quality >= 50")


def audit(path: Path) -> list[str]:
    """Problems with one written file; an empty list means clean."""
    problems = []
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        problems.append(f"{len(data)} bytes > {MAX_BYTES}")
    for name, marker in FORBIDDEN_MARKERS.items():
        if marker in data:
            problems.append(f"{name} marker present")
    with Image.open(path) as im:
        if max(im.size) > MAX_SIDE:
            problems.append(f"size {im.size} > {MAX_SIDE}")
        if len(im.getexif()):
            problems.append(f"{len(im.getexif())} EXIF tag(s)")
        for key in ("exif", "icc_profile", "xmp", "XML:com.adobe.xmp", "comment", "photoshop"):
            if key in im.info:
                problems.append(f"info[{key!r}] present")
    return problems


def prepare(src: Path, out: Path, exclude: set[str]) -> dict[str, Any]:
    labels = read_labels(src / "labels.csv")
    photos_out = out / "photos"
    photos_out.mkdir(parents=True, exist_ok=True)
    kept, excluded, name_map = [], [], {}
    for row in labels:
        if row["file"] in exclude:
            excluded.append(row["file"])
            continue
        new_name = f"photo_{len(kept) + 1:02d}.jpg"
        (photos_out / new_name).write_bytes(clean_jpeg(src / row["file"]))
        name_map[row["file"]] = new_name
        kept.append({**row, "file": new_name})
    unknown = sorted(exclude - {r["file"] for r in labels})
    if unknown:
        raise ValueError(f"--exclude names not in labels.csv: {unknown}")
    report = {f: audit(photos_out / f) for f in sorted(name_map.values())}
    dirty = {f: p for f, p in report.items() if p}
    (out / "labels.json").write_text(json.dumps(kept, indent=1) + "\n", encoding="utf-8")
    (src / "name_map.json").write_text(json.dumps(name_map, indent=1) + "\n", encoding="utf-8")
    (src / "excluded.json").write_text(json.dumps(excluded, indent=1) + "\n", encoding="utf-8")
    return {"kept": len(kept), "excluded": excluded, "dirty": dirty}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=".local/photos")
    ap.add_argument("--out", required=True, help="e.g. eval/raw/vision_real_2026-09-28")
    ap.add_argument("--exclude", default="", help="comma-separated original filenames to leave out (faces, badges, logos)")
    args = ap.parse_args(argv)
    src, out = Path(args.src), Path(args.out)
    if not (src / "labels.csv").exists():
        print(f"no {src / 'labels.csv'}: put the photos and labels.csv under {src}/ first", file=sys.stderr)
        return 2
    res = prepare(src, out, {e.strip() for e in args.exclude.split(",") if e.strip()})
    if res["dirty"]:
        print(f"FAIL: metadata or size check failed, do not commit {out}: {json.dumps(res['dirty'])}", file=sys.stderr)
        return 1
    print(f"clean: {res['kept']} photo(s) -> {out / 'photos'}; excluded {len(res['excluded'])}: {res['excluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
