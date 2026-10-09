"""Render deck/slides.html to docs/deck.pdf (14 pages) and deck/png/slide_NN.png (1920x1080).

Needs web/node_modules (`make setup`) and a Chromium that Playwright can find
(`cd web && npx playwright install chromium`). Fonts come from Google Fonts; offline, the
system fallbacks in the CSS are used and the layout still fits.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

if not (ROOT / "web" / "node_modules" / "@playwright" / "test").exists():
    sys.exit("deck: web/node_modules is missing; run `make setup` first")
sys.exit(subprocess.call(["node", str(HERE / "render.mjs")], cwd=ROOT))
