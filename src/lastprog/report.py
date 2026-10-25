"""docs/backtest.md and the static plots page (German index.html, English en/index.html).

Inputs are committed files only: docs/results/<run_id>/{summary,run}.json and, for the live section, a
checkout of the forecast-log branch. Charts are matplotlib SVGs in a dark theme matching the portfolio hub;
categorical colours follow a fixed, validated order (CVD-checked against the panel colour #11161d).
"""

from __future__ import annotations

import html
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .evaluation import TABLE_MODELS  # noqa: E402
from .monitor import read_log, rolling_live_metrics  # noqa: E402

BG, PANEL, INK, MUTED, GRID = "#0B0F14", "#11161d", "#E6EDF3", "#8B949E", "#232a33"
ACCENT = "#F2A93B"
COLORS = {
    "lgbm_cqr": "#3987e5",
    "naive_week": "#d95926",
    "mstl_ets": "#199e70",
    "lgbm_qr": "#c98500",
    "tso_reference": "#d55181",
}
CHART_MODELS = ["lgbm_cqr", "naive_week", "mstl_ets", "lgbm_qr"]
LIVE_MIN_DAYS = 56
CREDIT = {
    "de": 'Daten: <a href="https://www.smard.de/">Bundesnetzagentur | SMARD.de</a> (CC BY 4.0)',
    "en": 'Data: <a href="https://www.smard.de/en">Bundesnetzagentur | SMARD.de</a> (CC BY 4.0)',
}
CREDIT_WX = {
    "de": ' · <a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a> (CC BY 4.0)',
    "en": ' · <a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a> (CC BY 4.0)',
}

TEXT = {
    "de": {
        "lang": "de",
        "title": "Netzlast-Prognose",
        "lead": "Kalibrierte probabilistische Day-ahead-Prognose der deutschen Netzlast (stündlich, Region DE).",
        "switch": '<a href="en/index.html">English</a>',
        "fan": "Neueste Prognose (Median, 50/80/90 %-Intervalle)",
        "fan_none": "Noch keine Live-Prognose im Log.",
        "table": "Backtest (gepoolt)",
        "reliability": "Zuverlässigkeitsdiagramm: nominal gegen empirisch",
        "pit": "PIT-Histogramm lgbm_cqr (gleichverteilt = kalibriert)",
        "hour": "CRPS nach Stunde (lokal)",
        "month": "CRPS nach Monat",
        "live": "Live-Vorwärtszeitraum: rollierender CRPS (28 Tage)",
        "live_note": "Vorläufig: weniger als acht Wochen bewertete Tage. Live-Zahlen werden erst danach zitiert.",
        "live_none": "Noch keine bewerteten Live-Tage.",
        "run": "Lauf",
        "model": "Modell",
        "x_hour": "Stunde",
        "x_time": "Zeit (Europe/Berlin)",
        "y_mwh": "MWh",
        "y_crps": "CRPS (MWh)",
        "nominal": "nominale Quantilstufe",
        "empirical": "empirischer Anteil y ≤ q",
        "actual": "Ist",
        "reference": "ÜNB-Prognose (411)",
        "median": "Median",
        "backtest_line": "Backtest-Mittel",
        "methods": 'Methode und Protokoll: <a href="https://github.com/HARISPAARTAN/netzlast-prognose">Repository</a>',
    },
    "en": {
        "lang": "en",
        "title": "Netzlast-Prognose (grid load forecast)",
        "lead": "Calibrated probabilistic day-ahead forecast of German grid load (hourly, region DE).",
        "switch": '<a href="../index.html">Deutsch</a>',
        "fan": "Latest forecast (median, 50/80/90 % intervals)",
        "fan_none": "No live forecast in the log yet.",
        "table": "Backtest (pooled)",
        "reliability": "Reliability diagram: nominal against empirical",
        "pit": "PIT histogram lgbm_cqr (flat = calibrated)",
        "hour": "CRPS by local hour",
        "month": "CRPS by month",
        "live": "Live forward period: rolling CRPS (28 days)",
        "live_note": "Preliminary: fewer than eight weeks of scored days. Live numbers are quoted only after that.",
        "live_none": "No scored live days yet.",
        "run": "Run",
        "model": "Model",
        "x_hour": "hour",
        "x_time": "time (Europe/Berlin)",
        "y_mwh": "MWh",
        "y_crps": "CRPS (MWh)",
        "nominal": "nominal quantile level",
        "empirical": "empirical share y ≤ q",
        "actual": "actual",
        "reference": "TSO forecast (411)",
        "median": "median",
        "backtest_line": "backtest mean",
        "methods": 'Method and protocol: <a href="https://github.com/HARISPAARTAN/netzlast-prognose">repository</a>',
    },
}


def _fig(width: float = 7.2, height: float = 3.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=100)
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_color(MUTED)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    return fig, ax


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    text = buf.getvalue()
    return text[text.index("<svg") :]


def _legend(ax) -> None:
    leg = ax.legend(frameon=False, fontsize=8, labelcolor=INK)
    if leg is not None:
        for line in leg.get_lines():
            line.set_linewidth(2)


def fan_chart(entry: dict, t: dict) -> str:
    doc = entry["models"]["lgbm_cqr"]
    pts = doc["points"]
    x = list(range(len(pts)))
    labels = [p["ts_local"][11:16] for p in pts]
    fig, ax = _fig()
    for lv, alpha in (("0.9", 0.18), ("0.8", 0.28), ("0.5", 0.42)):
        lo = [p["intervals"][lv][0] for p in pts]
        hi = [p["intervals"][lv][1] for p in pts]
        ax.fill_between(
            x, lo, hi, color=COLORS["lgbm_cqr"], alpha=alpha, linewidth=0, label=f"{float(lv):.0%}"
        )
    ax.plot(x, [p["median"] for p in pts], color=COLORS["lgbm_cqr"], linewidth=2, label=t["median"])
    scored = entry.get("scored")
    if scored:
        ax.plot(x, scored["actual"], color=INK, linewidth=2, label=t["actual"])
        if scored.get("reference"):
            ax.plot(
                x,
                scored["reference"],
                color=COLORS["tso_reference"],
                linewidth=2,
                linestyle="--",
                label=t["reference"],
            )
    ax.set_xticks(x[::3], labels[::3])
    ax.set_xlabel(f"{t['x_time']} · {entry['target_date_local']}")
    ax.set_ylabel(t["y_mwh"])
    _legend(ax)
    return _svg(fig)


def reliability_chart(summary: dict, t: dict) -> str:
    taus = summary["taus"]
    fig, ax = _fig(4.6, 4.0)
    ax.plot([0, 1], [0, 1], color=MUTED, linewidth=1, linestyle=":")
    for m in CHART_MODELS:
        if m in summary["reliability"]:
            ax.plot(
                taus,
                summary["reliability"][m],
                color=COLORS[m],
                linewidth=2,
                marker="o",
                markersize=3,
                label=m,
            )
    ax.set_xlabel(t["nominal"])
    ax.set_ylabel(t["empirical"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _legend(ax)
    return _svg(fig)


def pit_chart(summary: dict, t: dict, model: str = "lgbm_cqr") -> str:
    counts = summary["pit"][model]
    total = sum(counts)
    width = 1 / len(counts)
    density = [c / total / width for c in counts]
    fig, ax = _fig(4.6, 4.0)
    ax.bar(
        [i * width for i in range(len(counts))], density, width=width * 0.9, align="edge", color=COLORS[model]
    )
    ax.axhline(1.0, color=MUTED, linewidth=1, linestyle=":")
    ax.set_xlabel("PIT")
    ax.set_ylabel("density")
    return _svg(fig)


def by_hour_chart(summary: dict, t: dict) -> str:
    fig, ax = _fig()
    for m in CHART_MODELS:
        if m in summary["by_hour"]:
            ax.plot(range(24), summary["by_hour"][m], color=COLORS[m], linewidth=2, label=m)
    ax.set_xlabel(t["x_hour"])
    ax.set_ylabel(t["y_crps"])
    ax.set_xticks(range(0, 24, 3))
    _legend(ax)
    return _svg(fig)


def by_month_chart(summary: dict, t: dict) -> str:
    fig, ax = _fig()
    months = sorted(next(iter(summary["by_month"].values())).keys())
    for m in CHART_MODELS:
        if m in summary["by_month"]:
            ax.plot(
                range(len(months)),
                [summary["by_month"][m].get(k) for k in months],
                color=COLORS[m],
                linewidth=2,
                label=m,
            )
    step = max(1, -(-len(months) // 6))
    short = [f"{m[5:7]}/{m[2:4]}" for m in months]
    ax.set_xticks(range(0, len(months), step), short[::step])
    ax.set_ylabel(t["y_crps"])
    _legend(ax)
    return _svg(fig)


def live_chart(entries: list[dict], backtest_crps: float | None, t: dict) -> str | None:
    df = rolling_live_metrics(entries)
    if df.empty:
        return None
    fig, ax = _fig()
    ax.plot(range(len(df)), df["crps_roll"], color=COLORS["lgbm_cqr"], linewidth=2, label="lgbm_cqr")
    if backtest_crps is not None:
        ax.axhline(backtest_crps, color=MUTED, linewidth=1, linestyle="--", label=t["backtest_line"])
    step = max(1, len(df) // 8)
    ax.set_xticks(range(0, len(df), step), list(df["target_date"])[::step])
    ax.set_ylabel(t["y_crps"])
    _legend(ax)
    return _svg(fig)


def _table(summary: dict, t: dict) -> str:
    cols = ["crps", "mae", "mape", "cov_50", "cov_80", "cov_90", "width_80", "n_origins"]
    head = "".join(f"<th>{c}</th>" for c in [t["model"], *cols])
    rows = []
    for m in TABLE_MODELS:
        if m not in summary["models"]:
            continue
        v = summary["models"][m]
        cells = []
        for c in cols:
            x = v[c]
            cells.append(
                f"<td>{x:.3f}</td>"
                if c.startswith("cov")
                else f"<td>{x:,.0f}</td>"
                if c != "mape"
                else f"<td>{x:.2f}</td>"
            )
        rows.append(f"<tr><th scope=row>{m}</th>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


CSS = f"""
:root {{ color-scheme: dark; --bg:{BG}; --panel:{PANEL}; --ink:{INK}; --muted:{MUTED}; --accent:{ACCENT}; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 Inter, system-ui, sans-serif; }}
main {{ max-width: 960px; margin: 0 auto; padding: 32px 16px 64px; }}
h1 {{ font: 600 28px/1.2 "Space Grotesk", Inter, sans-serif; margin: 0 0 8px; }}
h2 {{ font: 600 18px/1.3 "Space Grotesk", Inter, sans-serif; margin: 40px 0 12px; }}
.mono, .credit, th, td {{ font-family: "JetBrains Mono", ui-monospace, monospace; }}
.lead {{ color: var(--muted); }}
a {{ color: var(--accent); }}
figure {{ margin: 0; background: var(--panel); border-radius: 8px; padding: 12px; overflow-x: auto; }}
figure svg {{ max-width: 100%; height: auto; }}
.credit {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }}
.note {{ border-left: 3px solid var(--accent); padding: 4px 12px; color: var(--muted); }}
.tablewrap {{ overflow-x: auto; background: var(--panel); border-radius: 8px; padding: 12px; }}
table {{ border-collapse: collapse; font-size: 13px; width: 100%; }}
th, td {{ padding: 6px 8px; text-align: right; border-bottom: 1px solid #232a33; white-space: nowrap; }}
th[scope=row], thead th:first-child {{ text-align: left; }}
header nav {{ float: right; font-size: 14px; }}
"""


def _section(title: str, body: str, credit: str) -> str:
    return (
        f"<section><h2>{html.escape(title)}</h2><figure>{body}</figure><p class=credit>{credit}</p></section>"
    )


def render_page(
    lang: str, summary: dict | None, run: dict | None, entries: list[dict], uses_weather: bool
) -> str:
    t = TEXT[lang]
    credit = CREDIT[lang] + (CREDIT_WX[lang] if uses_weather else "")
    parts = [f"<header><nav>{t['switch']}</nav><h1>{html.escape(t['title'])}</h1></header>"]
    parts.append(f"<p class=lead>{html.escape(t['lead'])}</p>")
    latest = next((e for e in reversed(entries) if "lgbm_cqr" in e.get("models", {})), None)
    parts.append(
        _section(t["fan"], fan_chart(latest, t), CREDIT[lang])
        if latest
        else f"<h2>{html.escape(t['fan'])}</h2><p class=note>{t['fan_none']}</p>"
    )
    if summary:
        run_line = ""
        if run:
            run_line = (
                f"<p class='credit'>{t['run']} {html.escape(run['run_id'])} · {run['period'][0]} – {run['period'][1]} · "
                f"git {run['git_sha'][:10]} · "
                f"store {run['store_hash'][:12]} · {run['runtime_s']:.0f} s</p>"
            )
        parts.append(
            f"<h2>{html.escape(t['table'])}</h2><div class=tablewrap>{_table(summary, t)}</div>{run_line}"
        )
        parts.append(
            "<div class=grid2>"
            + _section(t["reliability"], reliability_chart(summary, t), credit)
            + _section(t["pit"], pit_chart(summary, t), credit)
            + "</div>"
        )
        parts.append(_section(t["hour"], by_hour_chart(summary, t), credit))
        parts.append(_section(t["month"], by_month_chart(summary, t), credit))
    scored = [e for e in entries if e.get("scored")]
    bt = summary["models"]["lgbm_cqr"]["crps"] if summary and "lgbm_cqr" in summary["models"] else None
    if len(scored) < LIVE_MIN_DAYS:
        # No live metric is shown or quoted before LIVE_MIN_DAYS scored days; only the count appears.
        note = f"{t['live_note']} ({len(scored)}/{LIVE_MIN_DAYS})"
        parts.append(f"<h2>{html.escape(t['live'])}</h2><p class=note>{note}</p>")
    else:
        chart = live_chart(entries, bt, t)
        parts.append(_section(t["live"], chart, CREDIT[lang]) if chart else "")
    parts.append(f"<p class=credit>{t['methods']}</p>")
    body = "\n".join(parts)
    return (
        f"<!doctype html><html lang={t['lang']}><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(t['title'])}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>\n"
    )


def build_site(results_dir: Path, run_id: str, log_dir: Path | None, out_dir: Path) -> list[Path]:
    """Write out_dir/index.html (German) and out_dir/en/index.html (English)."""
    summary_path = Path(results_dir) / run_id / "summary.json"
    run_path = Path(results_dir) / run_id / "run.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else None
    entries = read_log(log_dir) if log_dir and Path(log_dir).exists() else []
    uses_weather = bool(summary and "lgbm_cqr_wx" in summary["models"])
    out_dir = Path(out_dir)
    (out_dir / "en").mkdir(parents=True, exist_ok=True)
    written = []
    for lang, path in (("de", out_dir / "index.html"), ("en", out_dir / "en" / "index.html")):
        path.write_text(render_page(lang, summary, run, entries, uses_weather), encoding="utf-8")
        written.append(path)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return written
