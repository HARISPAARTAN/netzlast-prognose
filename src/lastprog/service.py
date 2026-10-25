"""Training for serving, the model manifest, and forecast assembly used by the API, the CLI and the live job.

A served model is the backtest's monthly refit at origin `as_of`: LightGBM quantile models fit on the target
days of the trailing window before cutoff(as_of), plus the out-of-sample lgbm_qr forecasts of the origins just
before `as_of` (calibration.parquet, produced by a short backtest with the same refit rule). At serve time the
conformal window holds the newest of those origins and of the origins since `as_of`, re-forecast with the
served model (still out of sample, because it never saw data at or after cutoff(as_of)). A forecast is
therefore deterministic for (model version, target date, store snapshot).
"""

from __future__ import annotations

import csv
import hashlib
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
from .pipeline import PROTOCOL_TAG, build_environment, git_sha
from .store import Store
from .timekeys import cutoff_utc, issue_time_utc, local_labels, utc_labels

SERVED_MODELS = ("lgbm_cqr", "naive_week")
ATTRIBUTION_SMARD = "Bundesnetzagentur | SMARD.de (CC BY 4.0)"
ATTRIBUTION_OPEN_METEO = "Weather data by Open-Meteo.com (CC BY 4.0)"
# Target days outside this range are a client error (pandas cannot represent them, date arithmetic overflows).
SUPPORTED_DATES = (date(1900, 1, 1), date(2200, 12, 31))
MAX_DATA_AGE_HOURS = 48


class UnknownModel(KeyError):
    """404."""


class BadRequest(ValueError):
    """400."""


class DataNotReady(RuntimeError):
    """409: the store lacks load data up to the cut-off."""


class NoModel(RuntimeError):
    """503."""


class ModelIntegrityError(RuntimeError):
    """A model file does not match the sha256 recorded in its manifest."""


def model_version(as_of: date, build: int = 0) -> str:
    """YYYY.MM.<build>. A refit of the same month that must not replace an existing model gets a new build."""
    return f"{as_of.year}.{as_of.month:02d}.{build}"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def files_digest(manifest: dict) -> str | None:
    """One digest for a built model: sha256 over the sorted "name:sha256" lines of the manifest's files."""
    files = manifest.get("files_sha256")
    if not files:
        return None
    text = "".join(f"{name}:{sha}\n" for name, sha in sorted(files.items()))
    return hashlib.sha256(text.encode()).hexdigest()


def training_data_digest(store: Store, from_ts: pd.Timestamp, cutoff: pd.Timestamp) -> dict:
    """Digest of the load observations a refit can see: ts_utc and value of load_actual in [from_ts, cutoff).

    Unlike the store snapshot it ignores everything at or after the cut-off and anything older than the
    training horizon, so two stores that agree on the data actually used give the same digest.
    """
    s = store.series("load_actual")
    s = s[(s.index >= from_ts) & (s.index < cutoff)]
    body = pd.DataFrame({"ts_utc": s.index.asi8, "value": s.to_numpy("float64")})
    hashed = pd.util.hash_pandas_object(body, index=False).to_numpy()
    return {
        "series": "load_actual",
        "from_utc": from_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to_utc_exclusive": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": int(len(s)),
        "rows_missing": int(s.isna().sum()),
        "sha256": hashlib.sha256(hashed.tobytes()).hexdigest(),
    }


REFIT_LOG_COLUMNS = [
    "version",
    "as_of",
    "git_sha",
    "built_at_utc",
    "platform",
    "python",
    "lightgbm",
    "runner_image",
    "run_url",
    "training_data_sha256",
    "model_files_digest",
    "tarball_sha256",
    "note",
]


def append_refit_log(log_path: Path, manifest_path: Path, tarball: Path) -> dict:
    """Append one row for the model in `manifest_path`; a version that is already logged is refused."""
    log_path = Path(log_path)
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    built = m.get("built_on") or {}
    row = {
        "version": m["version"],
        "as_of": m["as_of"],
        "git_sha": m.get("git_sha"),
        "built_at_utc": built.get("built_at_utc"),
        "platform": built.get("platform"),
        "python": (built.get("versions") or {}).get("python"),
        "lightgbm": (built.get("versions") or {}).get("lightgbm"),
        "runner_image": built.get("runner_image"),
        "run_url": built.get("run_url"),
        "training_data_sha256": (m.get("training_data") or {}).get("sha256"),
        "model_files_digest": files_digest(m),
        "tarball_sha256": file_sha256(tarball),
        "note": "",
    }
    exists = log_path.exists()
    if exists:
        with log_path.open(encoding="utf-8", newline="") as fh:
            if any(r["version"] == row["version"] for r in csv.DictReader(fh)):
                raise ValueError(f"version {row['version']} is already in {log_path}; use a new build number")
    with log_path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REFIT_LOG_COLUMNS, lineterminator="\n")
        if not exists:
            w.writeheader()
        w.writerow({k: "" if v is None else v for k, v in row.items()})
    return row


def backtest_reference(run_id: str, models: dict) -> dict:
    """The manifest's `test_metrics`: figures of a backtest run, labelled as such.

    The served model is fitted through the end of the test period, so these are the out-of-sample figures of
    the monthly-refit procedure (each month scored by the model fitted before it), not a holdout of this fit.
    """
    return {
        "run_id": run_id,
        "protocol": PROTOCOL_TAG,
        "note": (
            f"Figures of the pre-registered {run_id} backtest under {PROTOCOL_TAG} (rolling origin, monthly "
            "refit, each month scored by the model fitted before it). They are not an evaluation of this "
            "served model, which was trained through the test period."
        ),
        "metrics": {k: models[k] for k in ("lgbm_cqr", "naive_week") if k in models},
    }


def train_model(
    settings: Settings,
    store: Store,
    as_of: date,
    out_root: Path,
    test_metrics: dict | None = None,
    build: int = 0,
) -> Path:
    """Fit the served lgbm_qr at origin `as_of`, write q_*.txt, calibration.parquet and manifest.json."""
    taus = taus_of(settings)
    spec = feature_spec(settings, with_weather=False)
    version = model_version(as_of, build)
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
    files_sha256 = {name: file_sha256(out_dir / name) for name in [*files, "calibration.parquet"]}
    # Everything a refit can read: the training window, the calibration backtest (conformal window origins, each
    # with its own three-year window) and the longest lag.
    horizon = settings.backtest.train_window_days + window + 1 + 14
    data_from = pd.Timestamp(as_of - timedelta(days=horizon), tz="UTC")
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
        "files_sha256": files_sha256,
        "git_sha": git_sha(settings.root),
        "protocol_tag": PROTOCOL_TAG,
        "store_hash": store.snapshot(),
        "training_data": training_data_digest(store, data_from, cutoff),
        "built_on": {
            **build_environment(),
            "built_at_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
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
        self._store_hash: str | None = None
        if model_dir is not None and (Path(model_dir) / "manifest.json").exists():
            self._load(Path(model_dir))

    def _load(self, model_dir: Path) -> None:
        self.manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in self.manifest.get("files_sha256", {}).items():
            if file_sha256(model_dir / name) != expected:
                raise ModelIntegrityError(f"{name} in {model_dir} does not match the manifest sha256")
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
        if not SUPPORTED_DATES[0] <= target_day <= SUPPORTED_DATES[1]:
            raise BadRequest(
                f"target_date must be between {SUPPORTED_DATES[0].isoformat()} and {SUPPORTED_DATES[1].isoformat()}"
            )
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

    def store_hash(self) -> str:
        """Snapshot hash of the store this instance serves from (computed once per instance)."""
        if self._store_hash is None:
            self._store_hash = self.store.snapshot()
        return self._store_hash

    def health(self, now: pd.Timestamp | None = None) -> dict:
        """Status "ok" or "degraded" (no model, or in full mode no load data or data older than 48 h)."""
        last = self.store.last_observed("load_actual")
        last_s = None if last is None else last.strftime("%Y-%m-%dT%H:%M:%SZ")
        problems = []
        if self.model is None:
            problems.append("no model loaded")
        if self.settings.mode == "demo":
            age = None
        else:
            now = now or pd.Timestamp.now(tz="UTC")
            age = None if last is None else round((now - last) / pd.Timedelta(hours=1), 1)
            if age is None:
                problems.append("store holds no load data")
            elif age > MAX_DATA_AGE_HOURS:
                problems.append(f"newest load data is {age} h old (limit {MAX_DATA_AGE_HOURS} h)")
        m = self.manifest or {}
        return {
            "status": "degraded" if problems else "ok",
            "problems": problems,
            "model": self.settings.model.headline if self.model is not None else None,
            "model_version": m.get("version"),
            "model_git_sha": m.get("git_sha"),
            "model_store_hash": m.get("store_hash"),
            "model_files_digest": files_digest(m),
            "protocol_tag": m.get("protocol_tag"),
            "store_hash": self.store_hash(),
            "data_last_ts_utc": last_s,
            "data_age_hours": age,
            "mode": self.settings.mode,
        }

    def models(self) -> list[dict]:
        if self.manifest is None:
            raise NoModel("no model loaded")
        m = self.manifest
        ref = m.get("test_metrics") or {}
        if "metrics" not in ref:  # manifest written before the run id was recorded
            ref = {
                "run_id": None,
                "protocol": None,
                "note": "Backtest figures of the refit procedure, not an evaluation of this served model.",
                "metrics": ref,
            }

        def reference(name: str) -> dict:
            return {
                **{k: v for k, v in ref.items() if k != "metrics"},
                "metrics": ref["metrics"].get(name, {}),
            }

        return [
            {
                "name": "lgbm_cqr",
                "version": m["version"],
                "training_window": m["training_window"],
                "trained_until": m["trained_until"],
                "features": m["features"],
                "git_sha": m.get("git_sha"),
                "store_hash": m.get("store_hash"),
                "training_data": m.get("training_data"),
                "built_on": m.get("built_on"),
                "model_files_digest": files_digest(m),
                "protocol_tag": m.get("protocol_tag"),
                "files_sha256": m.get("files_sha256", {}),
                "test_metrics": reference("lgbm_cqr"),
            },
            {
                "name": "naive_week",
                "version": "n/a",
                "training_window": None,
                "trained_until": None,
                "features": ["lag_d6"],
                "protocol_tag": m.get("protocol_tag"),
                "test_metrics": reference("naive_week"),
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
