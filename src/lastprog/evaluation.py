"""Scores, slices, significance tests and pre-registered hypotheses for a backtest result."""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pandas as pd

from .backtest import BacktestResult
from .dmtest import dm_test
from .features import HolidayCalendar
from .metrics import INTERVAL_LEVELS, missing_rows, point_scores
from .models.conformal import unadjusted_rows
from .store import Store
from .timekeys import BERLIN, hours_in_day

SUMMARY_METRICS = ["pinball", "crps", "mae", "rmse", "mape", "mase"] + [
    f"{m}_{int(lv * 100)}" for m in ("cov", "width", "winkler") for lv in INTERVAL_LEVELS
]
REFERENCE = "tso_reference"
TABLE_MODELS = [
    "lgbm_cqr",
    "lgbm_qr",
    "lgbm_cqr_dp",
    "lgbm_aci",
    "lgbm_cqr_wx",
    "mstl_ets",
    "naive_week",
    "naive_day",
    "tso_reference",
]


def score_points(result: BacktestResult, store: Store) -> pd.DataFrame:
    """One row per model, origin and target hour with every per-point score (truth: the full store)."""
    load = store.series("load_actual")
    parts = []
    for model, by_origin in result.outputs.items():
        for origin, (idx, q) in by_origin.items():
            y = load.reindex(idx).to_numpy("float64")
            sc = point_scores(y, q, result.taus)
            frame = pd.DataFrame(sc)
            frame.insert(0, "y", y)
            frame.insert(0, "target_ts_utc", idx)
            frame.insert(0, "origin_date", pd.Timestamp(origin))
            frame.insert(0, "model", model)
            parts.append(frame)
    points = pd.concat(parts, ignore_index=True)
    return points[np.isfinite(points["crps"]) & np.isfinite(points["y"])].reset_index(drop=True)


def exclusion_counts(result: BacktestResult, store: Store) -> dict[str, dict[str, int]]:
    """Per model, over all scored origins and hours: rows, rows left out of every mean and why.

    `n_excluded` rows have a NaN target or a NaN quantile (never counted as a miss); `n_unadjusted` is the
    part of them whose forecast grid is NaN, i.e. rows a post-processing step (residual quantiles, conformal
    calibration) could not adjust for lack of a usable window, as at the start of a period.
    """
    load = store.series("load_actual")
    out: dict[str, dict[str, int]] = {}
    for model, by_origin in result.outputs.items():
        n_rows = n_excluded = n_unadjusted = n_no_target = 0
        for _origin, (idx, q) in by_origin.items():
            y = load.reindex(idx).to_numpy("float64")
            n_rows += len(idx)
            n_excluded += int(missing_rows(y, q).sum())
            n_unadjusted += unadjusted_rows(q)
            n_no_target += int(np.isnan(y).sum())
        out[model] = {
            "n_rows": n_rows,
            "n_excluded": n_excluded,
            "n_unadjusted": n_unadjusted,
            "n_missing_target": n_no_target,
        }
    return out


def per_origin(points: pd.DataFrame) -> pd.DataFrame:
    """metrics.parquet: model, origin_date, n_hours and the mean of every score per origin."""
    cols = [
        c
        for c in points.columns
        if c not in ("model", "origin_date", "target_ts_utc", "y", "median", "pit_bin")
    ]
    out = points.groupby(["model", "origin_date"], sort=True)[cols].mean().reset_index()
    out.insert(2, "n_hours", points.groupby(["model", "origin_date"], sort=True).size().to_numpy())
    return out


def _pooled(p: pd.DataFrame, naive_mae: float | None) -> dict:
    out = {
        "n_origins": int(p["origin_date"].nunique()),
        "n_points": len(p),
        "pinball": float(p["pinball"].mean()),
        "crps": float(p["crps"].mean()),
        "mae": float(p["abs_err"].mean()),
        "rmse": float(math.sqrt(p["sq_err"].mean())),
        "mape": float(p["ape"].mean() * 100.0),
        "mase": float(p["abs_err"].mean() / naive_mae) if naive_mae else math.nan,
    }
    for lv in INTERVAL_LEVELS:
        k = int(lv * 100)
        out[f"cov_{k}"] = float(p[f"cov_{k}"].mean())
        out[f"width_{k}"] = float(p[f"width_{k}"].mean())
        out[f"winkler_{k}"] = float(p[f"winkler_{k}"].mean())
    return out


def common_points(points: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """Rows of `models` restricted to (origin, hour) keys that every one of them has."""
    sub = points[points["model"].isin(models)]
    counts = sub.groupby(["origin_date", "target_ts_utc"])["model"].transform("nunique")
    return sub[counts == len(models)]


def daily_crps(points: pd.DataFrame, model: str) -> pd.Series:
    return points[points["model"] == model].groupby("origin_date")["crps"].mean()


def _dm(points: pd.DataFrame, a: str, b: str, lag: int) -> dict:
    da, db = daily_crps(points, a), daily_crps(points, b)
    both = da.index.intersection(db.index)
    res = dm_test(da[both].to_numpy(), db[both].to_numpy(), lag=lag)
    return res.as_dict()


def _slice_flags(points: pd.DataFrame, calendar: HolidayCalendar) -> pd.DataFrame:
    local = pd.DatetimeIndex(points["target_ts_utc"]).tz_convert(BERLIN)
    days = pd.Series(local.date, index=points.index)
    uniq = {d: d for d in days.unique()}
    hol = {d: calendar.share(d) >= 0.5 for d in uniq}
    bridge = {d: calendar.is_bridge(d) for d in uniq}
    dst = {d: hours_in_day(d) != 24 for d in uniq}
    return pd.DataFrame(
        {
            "hour": local.hour,
            "weekday": local.weekday,
            "month": [f"{t.year}-{t.month:02d}" for t in local],
            "year": local.year,
            "holiday": days.map(hol).to_numpy(),
            "bridge": days.map(bridge).to_numpy(),
            "dst_day": days.map(dst).to_numpy(),
            "xmas_week": [(t.month == 12 and t.day >= 24) for t in local],
        },
        index=points.index,
    )


def summarise(
    points: pd.DataFrame,
    taus: np.ndarray,
    calendar: HolidayCalendar,
    dm_lag: int,
    headline: str = "lgbm_cqr",
    baseline: str = "naive_week",
    weather_start: date | None = None,
) -> dict:
    """Everything docs/backtest.md and the plots page need, as plain JSON-serialisable data."""
    models = sorted(points["model"].unique())
    core = [m for m in models if m != REFERENCE]
    common = common_points(points, core) if core else points.iloc[0:0]
    naive_mae = float(common[common["model"] == baseline]["abs_err"].mean()) if baseline in core else None
    summary: dict = {"models": {}, "reliability": {}, "pit": {}, "by_hour": {}, "by_month": {}, "slices": {}}
    for m in models:
        if m == REFERENCE:
            p = (
                common_points(points, [REFERENCE, baseline])
                if baseline in models
                else points[points.model == m]
            )
            ref_naive = float(p[p["model"] == baseline]["abs_err"].mean()) if baseline in models else None
            p = p[p["model"] == m]
            summary["models"][m] = _pooled(p, ref_naive)
        else:
            p = common[common["model"] == m]
            summary["models"][m] = _pooled(p, naive_mae)
        k = len(taus)
        ranks = p["pit_bin"].to_numpy()
        summary["reliability"][m] = [float(np.mean(ranks <= j)) for j in range(k)]
        summary["pit"][m] = [int(np.sum(ranks == j)) for j in range(k + 1)]
        flags = _slice_flags(p, calendar)
        summary["by_hour"][m] = [float(v) for v in p.groupby(flags["hour"])["crps"].mean().reindex(range(24))]
        summary["by_month"][m] = {
            str(i): float(v) for i, v in p.groupby(flags["month"])["crps"].mean().items()
        }
        slices = {}
        for name in ("weekday", "year", "holiday", "bridge", "dst_day", "xmas_week"):
            for key, grp in p.groupby(flags[name]):
                slices[f"{name}={key}"] = {
                    "n": len(grp),
                    "crps": float(grp["crps"].mean()),
                    "mae": float(grp["abs_err"].mean()),
                    "cov_80": float(grp["cov_80"].mean()),
                    "cov_90": float(grp["cov_90"].mean()),
                }
        summary["slices"][m] = slices
    summary["dm"] = {}
    if headline in models:
        for other in models:
            if other != headline:
                pts = common if other != REFERENCE else common_points(points, [headline, REFERENCE])
                summary["dm"][f"{headline} vs {other}"] = _dm(pts, headline, other, dm_lag)
    summary["hypotheses"] = hypotheses(summary, points, dm_lag, headline, weather_start)
    summary["taus"] = [float(t) for t in taus]
    return summary


def hypotheses(
    summary: dict, points: pd.DataFrame, dm_lag: int, headline: str, weather_start: date | None
) -> dict:
    """H1 (DM 5 % vs naive_week and mstl_ets), H2 (80/90 % coverage within 2 points, closer than lgbm_qr), H3."""
    out: dict = {}
    dm = summary["dm"]
    h1 = {}
    for other in ("naive_week", "mstl_ets"):
        key = f"{headline} vs {other}"
        if key in dm:
            r = dm[key]
            h1[other] = {
                "p_a_better": r["p_a_better"],
                "supported": bool(r["mean_diff"] < 0 and r["p_a_better"] < 0.05),
            }
    if h1:
        out["H1"] = {"detail": h1, "supported": all(v["supported"] for v in h1.values())}
    mods = summary["models"]
    if headline in mods and "lgbm_qr" in mods:
        detail = {}
        for k in (80, 90):
            gap_c = abs(mods[headline][f"cov_{k}"] - k / 100)
            gap_q = abs(mods["lgbm_qr"][f"cov_{k}"] - k / 100)
            detail[str(k)] = {"gap_cqr": gap_c, "gap_qr": gap_q, "ok": bool(gap_c <= 0.02 and gap_c < gap_q)}
        out["H2"] = {"detail": detail, "supported": all(v["ok"] for v in detail.values())}
    if weather_start is not None and {headline, "lgbm_cqr_wx"} <= set(points["model"].unique()):
        sub = points[points["origin_date"] >= pd.Timestamp(weather_start)]
        sub = common_points(sub, [headline, "lgbm_cqr_wx"])
        r = _dm(sub, "lgbm_cqr_wx", headline, dm_lag)
        out["H3"] = {
            "detail": r,
            "crps_wx": float(sub[sub.model == "lgbm_cqr_wx"]["crps"].mean()),
            "crps_no_wx": float(sub[sub.model == headline]["crps"].mean()),
            "supported": bool(r["mean_diff"] < 0 and r["p_a_better"] < 0.05),
        }
    return out


def _fmt(v: float, key: str) -> str:
    if key.startswith("cov"):
        return f"{v:.3f}"
    if key in ("mape", "mase"):
        return f"{v:.3f}"
    return f"{v:,.1f}"


def results_markdown(summary: dict, run: dict) -> str:
    """Markdown block for one run: provenance line, pooled table, DM tests, hypotheses."""
    cols = [
        "crps",
        "pinball",
        "mae",
        "rmse",
        "mape",
        "mase",
        "cov_50",
        "cov_80",
        "cov_90",
        "width_80",
        "winkler_80",
    ]
    lines = [
        f"### Run `{run['run_id']}`",
        "",
        f"Command: `{run['command']}`  ",
        f"Git SHA: `{run['git_sha']}`{' (uncommitted changes)' if run.get('git_dirty') else ''} · store snapshot: `{run['store_hash']}` · config: `{run['config_hash'][:16]}` · "
        f"runtime: {run['runtime_s']:.0f} s · seed {run['seed']} · origins {run['period'][0]} to {run['period'][1]} "
        f"· cut-off rule `{run['cutoff_rule']}`",
        "",
        "| model | " + " | ".join(cols) + " | n_origins |",
        "|---|" + "---:|" * (len(cols) + 1),
    ]
    if run.get("protocol_v1") is False:
        lines[1:1] = [
            "",
            "**Not a protocol run:** scored without the `protocol-v1` tag (guard overridden); do not cite.",
        ]
    for m in TABLE_MODELS:
        if m in summary["models"]:
            v = summary["models"][m]
            lines.append(f"| {m} | " + " | ".join(_fmt(v[c], c) for c in cols) + f" | {v['n_origins']} |")
    if summary.get("excluded"):
        lines += [
            "",
            "| model | rows | excluded (NaN target or quantile) | unadjusted (NaN grid) | missing target |",
            "|---|---:|---:|---:|---:|",
        ]
        for m in TABLE_MODELS:
            if m in summary["excluded"]:
                e = summary["excluded"][m]
                lines.append(
                    f"| {m} | {e['n_rows']} | {e['n_excluded']} | {e['n_unadjusted']} | {e['n_missing_target']} |"
                )
    if summary.get("dm"):
        lines += [
            "",
            "| Diebold-Mariano (daily CRPS) | mean diff | statistic | p two-sided | p (A better) | n |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for k, r in summary["dm"].items():
            lines.append(
                f"| {k} | {r['mean_diff']:,.1f} | {r['statistic']:.3f} | {r['p_two_sided']:.4f} | "
                f"{r['p_a_better']:.4f} | {r['n']} |"
            )
    if summary.get("hypotheses"):
        lines += ["", "| Hypothesis | supported | detail |", "|---|---|---|"]
        for h, r in summary["hypotheses"].items():
            detail = json.dumps(r.get("detail", {}), sort_keys=True)
            lines.append(f"| {h} | {'yes' if r['supported'] else 'no'} | `{detail}` |")
    return "\n".join(lines) + "\n"
