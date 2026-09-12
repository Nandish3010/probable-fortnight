"""python -m data.generator --out .local/data --seed 20260912"""
from __future__ import annotations

import argparse
import json
import sys

from .generate import generate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=".local/data")
    ap.add_argument("--seed", type=int, default=20260912)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    manifest = generate(args.out, args.seed)
    if not args.quiet:
        print(json.dumps({"out": args.out, "seed": args.seed, "counts": manifest["counts"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
