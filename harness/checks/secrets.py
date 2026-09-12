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
    log = subprocess.run(["git", "log", "--format=%B", "-n", "50"], capture_output=True, text=True).stdout
    for name in ("attribution trailer", "assistant/model vendor name"):
        if PATTERNS[name].search(log):
            print(f"{name} in recent commit messages")
            bad += 1
    print("secrets: clean" if not bad else f"secrets: {bad} finding(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
