"""Training for serving, the model manifest, and forecast assembly used by the API, the CLI and the live job.

A served model is the backtest's monthly refit at origin `as_of`: LightGBM quantile models fit on the target
days of the trailing window before cutoff(as_of), plus the out-of-sample lgbm_qr forecasts of the origins just
before `as_of` (calibration.parquet, produced by a short backtest with the same refit rule). At serve time the
conformal window holds the newest of those origins and of the origins since `as_of`, re-forecast with the
served model (still out of sample, because it never saw data at or after cutoff(as_of)). A forecast is
therefore deterministic for (model version, target date, store snapshot).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import FeatureCache, feature_spec, run_backtest, taus_of
from .config import Settings
from .features import FeatureSpec, build_features
from .models.baselines import residual_quantiles
from .models.conformal import cqr_adjust
from .models.lgbm import LgbmQuantile
from .monitor import PSI_FEATURES, psi_reference
from .pipeline import git_sha
from .store import Store
from .timekeys import cutoff_utc, issue_time_utc, local_labels, utc_labels

SERVED_MODELS = ("lgbm_cqr", "naive_week")
ATTRIBUTION_SMARD = "Bundesnetzagentur | SMARD.de (CC BY 4.0)"
ATTRIBUTION_OPEN_METEO = "Weather data by Open-Meteo.com (CC BY 4.0)"


class UnknownModel(KeyError):
    """404."""


class BadRequest(ValueError):
    """400."""


class DataNotReady(RuntimeError):
    """409: the store lacks load data up to the cut-off."""


class NoModel(RuntimeError):
    """503."""


def model_version(as_of: date) -> str:
    return f"{as_of.year}.{as_of.month:02d}.0"


def train_model(
    settings: Settings, store: Store, as_of: date, out_root: Path, test_metrics: dict | None = None
) -> Path:
    """Fit the served lgbm_qr at origin `as_of`, write q_*.txt, calibration.parquet and manifest.json."""
    taus = taus_of(settings)
    spec = feature_spec(settings, with_weather=False)
    version = model_version(as_of)
    out_dir = Path(out_root) / version
    out_dir.mkdir(parents=True, exist_ok=True)

    window = settings.conformal.window_origins
    cal = run_backtest(
        settings, store, as_of - timedelta(days=window + 1), as_of - timedelta(days=1), ["lgbm_qr"]
    )
    rows = []
    for origin, (idx, q) in cal.outputs["lgbm_qr"].items():
        rows.append(
            pd.DataFrame(
                {
                    "origin_date": pd.Timestamp(origin),
                    "target_ts_utc": np.repeat(idx.to_numpy(), len(taus)),
                    "quantile": np.tile(taus, len(idx)),
                    "value": q.reshape(-1),
                }
            )
        )
    pd.concat(rows, ignore_index=True).to_parquet(out_dir / "calibration.parquet", index=False)

    cutoff = cutoff_utc(as_of, settings.cutoff_rule)
    cache = FeatureCache(store, spec, settings.cutoff_rule)
    X, y = cache.training_frame(as_of, cutoff, settings.backtest.train_window_days)
    m = settings.model
    model = LgbmQuantile("lgbm_qr", taus, m.lgbm, m.seed, m.num_threads, spec.columns)
    model.fit(X, y)
    files = model.save(out_dir)
    manifest = {
        "name": "lgbm_cqr",
        "base": "lgbm_qr",
        "version": version,
        "as_of": as_of.isoformat(),
        "trained_until": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "training_window": [
            (as_of - timedelta(days=settings.backtest.train_window_days)).isoformat(),
            (as_of - timedelta(days=1)).isoformat(),
        ],
        "training_rows": int(len(y)),
        "features": spec.columns,
        "hyperparameters": asdict(m.lgbm),
        "quantiles": [float(t) for t in taus],
        "conformal_window_origins": window,
        "residual_window_days": settings.backtest.residual_window_days,
        "seed": m.seed,
        "num_threads": m.num_threads,
        "files": files,
        "git_sha": git_sha(settings.root),
        "store_hash": store.snapshot(),
        "test_metrics": test_metrics or {},
        "psi_reference": {f: psi_reference(X[f].to_numpy("float64")) for f in PSI_FEATURES},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out_dir


class Forecaster:
    def __init__(self, settings: Settings, store: Store, model_dir: Path | None) -> None:
        self.settings = settings
        self.store = store
        self.taus = taus_of(settings)
        self.spec: FeatureSpec = feature_spec(settings, with_weather=False)
        self.manifest: dict | None = None
        self.model: LgbmQuantile | None = None
        self.calibration: dict[date, tuple[pd.DatetimeIndex, np.ndarray]] = {}
        self._raw_cache: dict[date, tuple[pd.DatetimeIndex, np.ndarray]] = {}
        if model_dir is not None and (Path(model_dir) / "manifest.json").exists():
            self._load(Path(model_dir))

    def _load(self, model_dir: Path) -> None:
        self.manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
        m = self.settings.model
        self.model = LgbmQuantile(
            "lgbm_qr", self.taus, m.lgbm, m.seed, m.num_threads, self.manifest["features"]
        )
        self.model.load(model_dir)
        cal = pd.read_parquet(model_dir / "calibration.parquet")
        for origin, grp in cal.groupby("origin_date", sort=True):
            grp = grp.sort_values(["target_ts_utc", "quantile"])
            idx = pd.DatetimeIndex(grp["target_ts_utc"].unique()).tz_convert("UTC")
            self.calibration[origin.date()] = (idx, grp["value"].to_numpy("float64").reshape(len(idx), -1))

    @property
    def as_of(self) -> date:
        if self.manifest is None:
            raise NoModel("no model loaded")
        return date.fromisoformat(self.manifest["as_of"])

    def _features(self, target_day: date) -> pd.DataFrame:
        cutoff = cutoff_utc(target_day - timedelta(days=1), self.settings.cutoff_rule)
        return build_features(self.store, target_day, cutoff, self.spec)

    def _raw_lgbm(self, origins: list[date]) -> dict[date, tuple[pd.DatetimeIndex, np.ndarray]]:
        """Served-model raw quantiles for origins >= as_of (memoised); calibration origins come from disk."""
        todo = [o for o in origins if o >= self.as_of and o not in self._raw_cache]
        if todo:
            frames = [self._features(o + timedelta(days=1)) for o in todo]
            q = self.model.predict_frame(pd.concat(frames))
            start = 0
            for o, f in zip(todo, frames, strict=True):
                self._raw_cache[o] = (f.index, q[start : start + len(f)])
                start += len(f)
        out = {}
        for o in origins:
            if o >= self.as_of:
                out[o] = self._raw_cache[o]
            elif o in self.calibration:
                out[o] = self.calibration[o]
        return out

    def check_data(self, issue_day: date, max_missing_hours: int) -> pd.Timestamp:
        cutoff = cutoff_utc(issue_day, self.settings.cutoff_rule)
        last = self.store.last_observed("load_actual")
        need = cutoff - pd.Timedelta(hours=1 + max_missing_hours)
        if last is None or last < need:
            newest = "none" if last is None else last.strftime("%Y-%m-%dT%H:%M:%SZ")
            raise DataNotReady(
                f"store has load data up to {newest}, needs {need.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                f"(cut-off {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')})"
            )
        return last

    def quantiles(
        self, target_day: date, model: str, max_missing_hours: int = 0
    ) -> tuple[pd.DatetimeIndex, np.ndarray]:
        if model not in SERVED_MODELS:
            raise UnknownModel(model)
        if self.model is None:
            raise NoModel("no model loaded")
        issue_day = target_day - timedelta(days=1)
        if issue_day < self.as_of:
            raise BadRequest(
                f"target_date must be after {self.as_of.isoformat()} (model {self.manifest['version']})"
            )
        self.check_data(issue_day, max_missing_hours)
        cutoff = cutoff_utc(issue_day, self.settings.cutoff_rule)
        load = self.store.series("load_actual")
        observed = load[load.index < cutoff]
        feats = self._features(target_day)
        if model == "naive_week":
            n = self.settings.backtest.residual_window_days
            origins = [issue_day - timedelta(days=k) for k in range(n + 1, 0, -1)]
            pts, ys = [], []
            for o in origins:
                f = self._features(o + timedelta(days=1))
                if f.index[-1] < cutoff:
                    pts.append(f["lag_d6"].to_numpy("float64"))
                    ys.append(observed.reindex(f.index).to_numpy("float64"))
            point = feats["lag_d6"].to_numpy("float64")
            resid = np.concatenate(ys) - np.concatenate(pts) if pts else np.empty(0)
            return feats.index, residual_quantiles(point, resid, self.taus)
        n = self.settings.conformal.window_origins
        candidates = [issue_day - timedelta(days=k) for k in range(n + 2, 0, -1)]
        raws = self._raw_lgbm(candidates)
        usable = [o for o in candidates if o in raws and raws[o][0][-1] < cutoff][-n:]
        raw = self.model.predict_frame(feats)
        if not usable:
            return feats.index, np.full_like(raw, np.nan)
        h_idx = pd.DatetimeIndex(np.concatenate([raws[o][0].to_numpy() for o in usable]))
        h_raw = np.concatenate([raws[o][1] for o in usable])
        y_hist = observed.reindex(h_idx).to_numpy("float64")
        return feats.index, cqr_adjust(raw, h_raw, y_hist, self.taus)

    def forecast(self, target_day: date, model: str | None = None, max_missing_hours: int = 0) -> dict:
        """The /forecast document."""
        model = model or self.settings.model.headline
        idx, q = self.quantiles(target_day, model, max_missing_hours)
        issue_day = target_day - timedelta(days=1)
        levels = list(self.settings.conformal.levels)
        t = np.round(self.taus, 4)
        med_col = int(np.flatnonzero(t == 0.5)[0])
        points = []
        for i, (ts_u, ts_l) in enumerate(zip(utc_labels(idx), local_labels(idx), strict=True)):
            intervals = {}
            for lv in levels:
                lo = int(np.flatnonzero(t == round((1 - lv) / 2, 4))[0])
                hi = int(np.flatnonzero(t == round(1 - (1 - lv) / 2, 4))[0])
                intervals[str(lv)] = [round(float(q[i, lo]), 2), round(float(q[i, hi]), 2)]
            points.append(
                {
                    "ts_utc": ts_u,
                    "ts_local": ts_l,
                    "median": round(float(q[i, med_col]), 2),
                    "quantiles": [round(float(v), 2) for v in q[i]],
                    "intervals": intervals,
                }
            )
        version = self.manifest["version"] if model == "lgbm_cqr" else "n/a"
        trained_until = self.manifest["trained_until"] if model == "lgbm_cqr" else None
        attribution = [ATTRIBUTION_SMARD] + ([ATTRIBUTION_OPEN_METEO] if self.spec.with_weather else [])
        return {
            "region": self.settings.data.region,
            "unit": "MWh",
            "timezone": "Europe/Berlin",
            "model": {"name": model, "version": version, "trained_until": trained_until},
            "issue_time_utc": utc_labels(
                pd.DatetimeIndex([issue_time_utc(issue_day, self.settings.issue_time_utc)])
            )[0],
            "information_cutoff_utc": utc_labels(
                pd.DatetimeIndex([cutoff_utc(issue_day, self.settings.cutoff_rule)])
            )[0],
            "target_date_local": target_day.isoformat(),
            "quantile_levels": [float(x) for x in self.taus],
            "interval_levels": levels,
            "points": points,
            "attribution": attribution,
        }

    def health(self, now: pd.Timestamp | None = None) -> dict:
        last = self.store.last_observed("load_actual")
        last_s = None if last is None else last.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self.settings.mode == "demo":
            age = None
            status = "ok" if self.model is not None else "degraded"
        else:
            now = now or pd.Timestamp.now(tz="UTC")
            age = None if last is None else round((now - last) / pd.Timedelta(hours=1), 1)
            status = "ok" if (self.model is not None and age is not None and age <= 48) else "degraded"
        return {
            "status": status,
            "model": self.settings.model.headline if self.model is not None else None,
            "model_version": self.manifest["version"] if self.manifest else None,
            "data_last_ts_utc": last_s,
            "data_age_hours": age,
            "mode": self.settings.mode,
        }

    def models(self) -> list[dict]:
        if self.manifest is None:
            raise NoModel("no model loaded")
        m = self.manifest
        return [
            {
                "name": "lgbm_cqr",
                "version": m["version"],
                "training_window": m["training_window"],
                "trained_until": m["trained_until"],
                "features": m["features"],
                "test_metrics": m.get("test_metrics", {}).get("lgbm_cqr", {}),
            },
            {
                "name": "naive_week",
                "version": "n/a",
                "training_window": None,
                "trained_until": None,
                "features": ["lag_d6"],
                "test_metrics": m.get("test_metrics", {}).get("naive_week", {}),
            },
        ]

    def default_target(self, now: pd.Timestamp | None = None) -> date:
        """Next local day in full mode; in demo mode the newest day the fixture data can serve."""
        if self.settings.mode == "demo":
            last = self.store.last_observed("load_actual")
            issue = (last + pd.Timedelta(hours=1)).tz_convert("Europe/Berlin").date()
            return issue + timedelta(days=1)
        now = now or pd.Timestamp.now(tz="UTC")
        return now.tz_convert("Europe/Berlin").date() + timedelta(days=1)
