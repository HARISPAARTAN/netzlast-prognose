"""Print Markdown slice tables (year, weekday 0 = Monday, holiday, bridge day, DST day, Christmas week,
month, hour) from a summary.json, for docs/backtest.md and docs/model-card.md.

Run: uv run python scripts/slice_tables.py docs/results/test-v1/summary.json [model ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GROUPS = ("year", "weekday", "holiday", "bridge", "dst_day", "xmas_week")


def main(path: str, models: list[str]) -> None:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    models = models or [m for m in ("lgbm_cqr", "naive_week") if m in summary["models"]]
    for group in GROUPS:
        keys = sorted({k for m in models for k in summary["slices"][m] if k.startswith(group + "=")})
        print(f"\n| {group} | " + " | ".join(f"{m} n | {m} CRPS | {m} cov80" for m in models) + " |")
        print("|---|" + "---:|---:|---:|" * len(models))
        for key in keys:
            cells = []
            for m in models:
                s = summary["slices"][m].get(key)
                cells += (
                    ["-", "-", "-"] if s is None else [str(s["n"]), f"{s['crps']:,.1f}", f"{s['cov_80']:.3f}"]
                )
            print(f"| {key.split('=', 1)[1]} | " + " | ".join(cells) + " |")
    print("\n| month | " + " | ".join(f"{m} CRPS" for m in models) + " |")
    print("|---|" + "---:|" * len(models))
    months = sorted({k for m in models for k in summary["by_month"][m]})
    for month in months:
        cells = [f"{summary['by_month'][m].get(month, float('nan')):,.1f}" for m in models]
        print(f"| {month} | " + " | ".join(cells) + " |")
    print("\n| hour (local) | " + " | ".join(f"{m} CRPS" for m in models) + " |")
    print("|---|" + "---:|" * len(models))
    for hour in range(24):
        cells = [f"{summary['by_hour'][m][hour]:,.1f}" for m in models]
        print(f"| {hour:02d} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
