"""Fail the build on secrets, attribution trailers, model-vendor names, or raw data in the tree."""
from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = {
    "private key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "google api key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "service account json": re.compile(r'"type"\s*:\s*"service_account"'),
    "attribution trailer": re.compile(r"^(Co-Authored-By|Claude-Session):", re.M),
    "assistant/model vendor name": re.compile(r"\b(claude|anthropic)\b", re.I),
}
RAW_DATA = re.compile(r"^data/public/raw/|\.(csv|parquet|zip)$", re.I)
ALLOW = {"harness/checks/secrets.py"}


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    bad = 0
    for f in files:
        if RAW_DATA.search(f):
            print(f"raw data tracked: {f}")
            bad += 1
            continue
        if f in ALLOW:
            continue
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for name, pat in PATTERNS.items():
            if pat.search(text):
                print(f"{name}: {f}")
                bad += 1
    # Scan only the commits this run is actually introducing (since the merge-base with the
    # default branch), not a fixed trailing window: a fixed window re-triggers forever on any
    # attribution trailer that ever lands in history, permanently red regardless of who pushes
    # next. On a PR this is exactly the new commits; on a push to main after merge, HEAD already
    # equals the base so there is nothing left to re-check -- the gate already ran at PR time.
    base_ref = None
    for ref in ("origin/main", "main"):
        if subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], capture_output=True).returncode == 0:
            base_ref = ref
            break
    if base_ref:
        merge_base = subprocess.run(["git", "merge-base", "HEAD", base_ref], capture_output=True, text=True).stdout.strip()
        log = subprocess.run(["git", "log", "--format=%B", f"{merge_base}..HEAD"], capture_output=True, text=True).stdout
    else:
        log = subprocess.run(["git", "log", "--format=%B", "-n", "50"], capture_output=True, text=True).stdout
    for name in ("attribution trailer", "assistant/model vendor name"):
        if PATTERNS[name].search(log):
            print(f"{name} in recent commit messages")
            bad += 1
    print("secrets: clean" if not bad else f"secrets: {bad} finding(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
