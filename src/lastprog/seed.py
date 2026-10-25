"""Seed CSV files under data/seed: leading lines starting with '#' name the source and licence."""

from __future__ import annotations

import csv
from pathlib import Path


def read_seed_csv(path: Path) -> list[dict]:
    """Rows of a seed CSV whose leading lines starting with '#' are source notes."""
    lines = [
        ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")
    ]
    return list(csv.DictReader(lines))
