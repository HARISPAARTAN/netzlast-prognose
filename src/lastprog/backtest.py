"""Rolling-origin backtest: one origin per day, issued on D for the local day D+1.

Every origin sees the store only through the cut-off (features, training rows, calibration outcomes).
LightGBM is refit on the first origin of the run and on the first origin of each calendar month, on the
target days of the trailing `train_window_days` that are fully observed before that origin's cut-off.
Residual-quantile and conformal models use the out-of-sample forecasts of the newest origins whose whole
target day lies before the cut-off; the run starts `warmup` origins early to fill that window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import Settings
from .features import FeatureSpec, HolidayCalendar, build_features, city_weights_from_seed
from .models.base import OriginInput
from .models.baselines import MstlEts, NaiveLag, TsoReference, residual_quantiles
from .models.conformal import AdaptiveConformal, cqr_adjust, daypart_of
from .models.lgbm import LgbmQuantile
from .store import Store
from .timekeys import BERLIN, cutoff_utc, daterange, issue_time_utc

# output model -> (base model, post-processing)
MODEL_SPECS: dict[str, tuple[str, str | None]] = {
    "naive_week": ("naive_week", "residual"),
    "naive_day": ("naive_day", "residual"),
    "mstl_ets": ("mstl_ets", None),
    "lgbm_qr": ("lgbm_qr", None),
    "lgbm_cqr": ("lgbm_qr", "cqr"),
    "lgbm_cqr_dp": ("lgbm_qr", "cqr_daypart"),
    "lgbm_aci": ("lgbm_qr", "aci"),
    "lgbm_cqr_wx": ("lgbm_qr_wx", "cqr"),
    "tso_reference": ("tso_reference", "residual"),
}
CORE_MODELS = [
    "naive_week",
    "naive_day",
    "mstl_ets",
    "lgbm_qr",
    "lgbm_cqr",
    "lgbm_cqr_dp",
    "lgbm_aci",
    "tso_reference",
]
TEST_MODELS = CORE_MODELS + ["lgbm_cqr_wx"]


def taus_of(settings: Settings) -> np.ndarray:
    return np.array(settings.model.quantiles, dtype="float64")


def feature_spec(settings: Settings, with_weather: bool) -> FeatureSpec:
    calendar = HolidayCalendar.from_seed(settings.paths.seed)
    weights = city_weights_from_seed(settings.paths.seed) if with_weather else {}
    return FeatureSpec(
        calendar=calendar,
        with_weather=with_weather,
        weather_offset_days=settings.weather.offset_days,
        city_weights=weights,
    )


class FeatureCache:
    """Features per target day, each computed once with the cut-off of its own issue day."""

    def __init__(self, store: Store, spec: FeatureSpec, cutoff_rule: str) -> None:
        self.store = store
        self.spec = spec
        self.cutoff_rule = cutoff_rule
        self._cache: dict[date, pd.DataFrame] = {}

    def get(self, target_day: date) -> pd.DataFrame:
        if target_day not in self._cache:
            cutoff = cutoff_utc(target_day - timedelta(days=1), self.cutoff_rule)
            self._cache[target_day] = build_features(self.store, target_day, cutoff, self.spec)
        return self._cache[target_day]

    def training_frame(
        self, origin: date, cutoff: pd.Timestamp, window_days: int
    ) -> tuple[pd.DataFrame, np.ndarray]:
        """Rows of the target days [origin - window_days, origin - 1] observed before `cutoff`."""
        load = self.store.series("load_actual")
        observed = load[load.index < cutoff]
        frames = [self.get(origin - timedelta(days=k)) for k in range(window_days, 0, -1)]
        X = pd.concat(frames)
        X = X[X.index < cutoff]
        y = observed.reindex(X.index).to_numpy("float64")
        keep = ~np.isnan(y)
        return X[keep], y[keep]


def make_bases(settings: Settings, base_names: set[str], columns: dict[str, list[str]]) -> dict:
    taus = taus_of(settings)
    m = settings.model
    factories = {
        "naive_week": lambda: NaiveLag("naive_week", "lag_d6"),
        "naive_day": lambda: NaiveLag("naive_day", "lag_d1"),
        "tso_reference": TsoReference,
        "mstl_ets": lambda: MstlEts(taus, m.mstl_season_lengths, m.mstl_train_days),
        "lgbm_qr": lambda: LgbmQuantile("lgbm_qr", taus, m.lgbm, m.seed, m.num_threads, columns["base"]),
        "lgbm_qr_wx": lambda: LgbmQuantile(
            "lgbm_qr_wx", taus, m.lgbm, m.seed, m.num_threads, columns["weather"]
        ),
    }
    return {name: factories[name]() for name in sorted(base_names)}


@dataclass
class BacktestResult:
    taus: np.ndarray
    origins: list[date]  # scored origins
    outputs: dict[str, dict[date, tuple[pd.DatetimeIndex, np.ndarray]]]
    cutoff_rule: str
    runtime_s: float = 0.0
    fits: dict[str, list[str]] = field(default_factory=dict)


def warmup_for(settings: Settings, models: list[str]) -> int:
    posts = {MODEL_SPECS[m][1] for m in models}
    if posts == {None}:
        return 0
    return max(settings.conformal.window_origins, settings.backtest.residual_window_days) + 1


def _window(
    history: dict[date, tuple[pd.DatetimeIndex, np.ndarray]], origin: date, cutoff: pd.Timestamp, n: int
) -> list[date]:
    """The newest `n` earlier origins whose whole target day lies before `cutoff`, oldest first."""
    chosen: list[date] = []
    for o in reversed(list(history)):
        if o >= origin:
            continue
        if history[o][0][-1] < cutoff:
            chosen.append(o)
            if len(chosen) == n:
                break
    return chosen[::-1]


def run_backtest(
    settings: Settings,
    store: Store,
    first_origin: date,
    last_origin: date,
    models: list[str],
    cutoff_rule: str | None = None,
    progress: bool = False,
) -> BacktestResult:
    unknown = [m for m in models if m not in MODEL_SPECS]
    if unknown:
        raise ValueError(f"unknown models {unknown}; known: {sorted(MODEL_SPECS)}")
    rule = cutoff_rule or settings.cutoff_rule
    taus = taus_of(settings)
    with_weather = any(MODEL_SPECS[m][0] == "lgbm_qr_wx" for m in models)
    spec = feature_spec(settings, with_weather)
    base_cols = [c for c in spec.columns if not c.startswith("wx_")]
    cache = FeatureCache(store, spec, rule)
    bases = make_bases(
        settings, {MODEL_SPECS[m][0] for m in models}, {"base": base_cols, "weather": spec.columns}
    )
    warmup = warmup_for(settings, models)
    origins = daterange(first_origin - timedelta(days=warmup), last_origin)
    history: dict[str, dict] = {b: {} for b in bases}
    outputs: dict[str, dict] = {m: {} for m in models}
    aci = {
        m: AdaptiveConformal(taus, settings.conformal.aci_gamma) for m in models if MODEL_SPECS[m][1] == "aci"
    }
    aci_done: dict[str, set] = {m: set() for m in aci}
    fits: dict[str, list[str]] = {b: [] for b in bases}
    load = store.series("load_actual")
    started = time.perf_counter()

    for i, origin in enumerate(origins):
        target = origin + timedelta(days=1)
        cutoff = cutoff_utc(origin, rule)
        feats = cache.get(target)
        inp = OriginInput(origin, target, cutoff, feats.index, feats, store)
        observed = load[load.index < cutoff]
        raws: dict[str, np.ndarray] = {}
        for name, base in bases.items():
            if isinstance(base, LgbmQuantile):
                if base.fitted_at is None or (origin.year, origin.month) != (
                    base.fitted_at.year,
                    base.fitted_at.month,
                ):
                    X, y = cache.training_frame(origin, cutoff, settings.backtest.train_window_days)
                    base.fit(X, y)
                    base.fitted_at = origin
                    fits[name].append(origin.isoformat())
            raws[name] = base.predict(inp)
            history[name][origin] = (inp.index, raws[name])
        for model in models:
            bname, post = MODEL_SPECS[model]
            raw = raws[bname]
            if post is None:
                q = raw
            else:
                n = (
                    settings.backtest.residual_window_days
                    if post == "residual"
                    else settings.conformal.window_origins
                )
                win = _window(history[bname], origin, cutoff, n)
                if win:
                    h_idx = pd.DatetimeIndex(np.concatenate([history[bname][o][0].to_numpy() for o in win]))
                    h_raw = np.concatenate([history[bname][o][1] for o in win])
                    y_hist = observed.reindex(h_idx).to_numpy("float64")
                else:
                    h_idx = pd.DatetimeIndex([], tz="UTC")
                    h_raw = np.empty((0,) if post == "residual" else (0, len(taus)))
                    y_hist = np.empty(0)
                if post == "residual":
                    q = residual_quantiles(raw, y_hist - h_raw, taus)
                elif post == "cqr":
                    q = cqr_adjust(raw, h_raw, y_hist, taus)
                elif post == "cqr_daypart":
                    g = daypart_of(inp.index.tz_convert(BERLIN).hour.to_numpy())
                    gh = daypart_of(h_idx.tz_convert(BERLIN).hour.to_numpy())
                    q = cqr_adjust(raw, h_raw, y_hist, taus, g, gh)
                elif post == "aci":
                    for o in _window(outputs[model], origin, cutoff, len(outputs[model])):
                        if o not in aci_done[model]:
                            p_idx, p_q = outputs[model][o]
                            aci[model].update(p_q, observed.reindex(p_idx).to_numpy("float64"))
                            aci_done[model].add(o)
                    q = aci[model].adjust(raw, h_raw, y_hist) if win else np.full_like(raw, np.nan)
                else:
                    raise ValueError(post)
            outputs[model][origin] = (inp.index, q)
        if progress and (i % 30 == 0 or origin == last_origin):
            print(f"{origin} {i + 1}/{len(origins)} {time.perf_counter() - started:.0f}s", flush=True)

    scored = [o for o in origins if o >= first_origin]
    outputs = {m: {o: v for o, v in d.items() if o >= first_origin} for m, d in outputs.items()}
    return BacktestResult(taus, scored, outputs, rule, time.perf_counter() - started, fits)


def forecasts_frame(
    result: BacktestResult, settings: Settings, model_version: str = "backtest"
) -> pd.DataFrame:
    """Long frame: model, model_version, origin_date, issue_time_utc, cutoff_utc, target_ts_utc, lead_h,
    quantile, value."""
    parts = []
    k = len(result.taus)
    for model, by_origin in result.outputs.items():
        for origin, (idx, q) in by_origin.items():
            issue = issue_time_utc(origin, settings.issue_time_utc)
            n = len(idx)
            lead = ((idx - issue) / pd.Timedelta(hours=1)).to_numpy()
            parts.append(
                pd.DataFrame(
                    {
                        "model": model,
                        "model_version": model_version,
                        "origin_date": pd.Timestamp(origin),
                        "issue_time_utc": issue,
                        "cutoff_utc": cutoff_utc(origin, result.cutoff_rule),
                        "target_ts_utc": np.repeat(idx.to_numpy(), k),
                        "lead_h": np.repeat(lead, k),
                        "quantile": np.tile(result.taus, n),
                        "value": q.reshape(-1),
                    }
                )
            )
    return pd.concat(parts, ignore_index=True)
