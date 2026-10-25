"""Settings from config.toml, overridable by environment variables.

Environment: LASTPROG_CONFIG (path of config.toml), LASTPROG_DATA_DIR (base for raw, store and models),
LASTPROG_MODE (`full` or `demo`), LASTPROG_OFFLINE=1 (every HTTP call raises), LASTPROG_LOG_LEVEL.
`Settings.for_fixtures()` applies the [fixtures] overrides used by `--period fixtures` and demo mode.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.toml"


@dataclass(frozen=True)
class DataCfg:
    region: str
    load_filter: int
    reference_filter: int
    price_filter: int
    price_region: str
    resolution: str
    history_start: date
    smard_base_url: str
    min_request_interval_s: float
    user_agent: str


@dataclass(frozen=True)
class LgbmParams:
    n_estimators: int
    learning_rate: float
    num_leaves: int
    min_child_samples: int
    feature_fraction: float
    lambda_l2: float


@dataclass(frozen=True)
class ModelCfg:
    quantiles: tuple[float, ...]
    seed: int
    num_threads: int
    headline: str
    lgbm: LgbmParams
    mstl_season_lengths: tuple[int, ...]
    mstl_train_days: int


@dataclass(frozen=True)
class BacktestCfg:
    validation: tuple[date, date]
    test: tuple[date, date]
    weather_test_start: date
    train_window_days: int
    refit: str
    dm_lag: int
    residual_window_days: int
    fixtures: tuple[date, date]


@dataclass(frozen=True)
class ConformalCfg:
    window_origins: int
    levels: tuple[float, ...]
    aci_gamma: float


@dataclass(frozen=True)
class WeatherCfg:
    enabled: bool
    api: str
    base_url: str
    offset_days: int
    variables: tuple[str, ...]
    start: date


@dataclass(frozen=True)
class PathsCfg:
    raw: Path
    store: Path
    runs: Path
    models: Path
    fixtures: Path
    seed: Path
    site: Path
    results: Path


@dataclass(frozen=True)
class Settings:
    root: Path
    data: DataCfg
    issue_time_utc: str
    cutoff_rule: str
    backtest: BacktestCfg
    model: ModelCfg
    conformal: ConformalCfg
    weather: WeatherCfg
    paths: PathsCfg
    fixture_overrides: dict
    mode: str
    offline: bool
    is_fixtures: bool = False

    def for_fixtures(self) -> Settings:
        """Copy with the [fixtures] overrides: short windows, one thread, small LightGBM models.

        Every LightGBM parameter comes from [fixtures], so tuning [model.lgbm] never changes the golden file.
        """
        fx = self.fixture_overrides
        lgbm = LgbmParams(
            n_estimators=int(fx["n_estimators"]),
            learning_rate=float(fx["learning_rate"]),
            num_leaves=int(fx["num_leaves"]),
            min_child_samples=int(fx["min_child_samples"]),
            feature_fraction=float(fx["feature_fraction"]),
            lambda_l2=float(fx["lambda_l2"]),
        )
        model = replace(
            self.model,
            num_threads=int(fx["num_threads"]),
            lgbm=lgbm,
            mstl_train_days=int(fx["mstl_train_days"]),
        )
        backtest = replace(
            self.backtest,
            train_window_days=int(fx["train_window_days"]),
            residual_window_days=int(fx["residual_window_days"]),
        )
        conformal = replace(self.conformal, window_origins=int(fx["window_origins"]))
        return replace(self, model=model, backtest=backtest, conformal=conformal, is_fixtures=True)

    @property
    def demo_as_of(self) -> date:
        return date.fromisoformat(self.fixture_overrides["demo_as_of"])


def _d(value: str) -> date:
    return date.fromisoformat(value)


def load_settings(path: Path | None = None) -> Settings:
    """Read config.toml (LASTPROG_CONFIG or the repository default) and apply environment overrides."""
    cfg_path = Path(path or os.environ.get("LASTPROG_CONFIG") or DEFAULT_CONFIG).resolve()
    raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    root = cfg_path.parent
    d, m, b, c, w, p = (
        raw["data"],
        raw["model"],
        raw["backtest"],
        raw["conformal"],
        raw["weather"],
        raw["paths"],
    )

    data = DataCfg(
        region=d["region"],
        load_filter=int(d["load_filter"]),
        reference_filter=int(d["reference_filter"]),
        price_filter=int(d["price_filter"]),
        price_region=d["price_region"],
        resolution=d["resolution"],
        history_start=_d(d["history_start"]),
        smard_base_url=d["smard_base_url"],
        min_request_interval_s=float(d["min_request_interval_s"]),
        user_agent=d["user_agent"],
    )
    model = ModelCfg(
        quantiles=tuple(round(float(q), 4) for q in m["quantiles"]),
        seed=int(m["seed"]),
        num_threads=int(m["num_threads"]),
        headline=m["headline"],
        lgbm=LgbmParams(**m["lgbm"]),
        mstl_season_lengths=tuple(int(s) for s in m["mstl"]["season_lengths"]),
        mstl_train_days=int(m["mstl"]["train_days"]),
    )
    fx = raw["fixtures"]
    backtest = BacktestCfg(
        validation=(_d(b["validation"][0]), _d(b["validation"][1])),
        test=(_d(b["test"][0]), _d(b["test"][1])),
        weather_test_start=_d(b["weather_test_start"]),
        train_window_days=int(b["train_window_days"]),
        refit=b["refit"],
        dm_lag=int(b["dm_lag"]),
        residual_window_days=int(b["residual_window_days"]),
        fixtures=(_d(fx["origins"][0]), _d(fx["origins"][1])),
    )
    conformal = ConformalCfg(
        window_origins=int(c["window_origins"]),
        levels=tuple(float(x) for x in c["levels"]),
        aci_gamma=float(c["aci_gamma"]),
    )
    weather = WeatherCfg(
        enabled=bool(w["enabled"]),
        api=w["api"],
        base_url=w["base_url"],
        offset_days=int(w["offset_days"]),
        variables=tuple(w["variables"]),
        start=_d(w["start"]),
    )
    paths = {k: (root / v) for k, v in p.items()}
    data_dir = os.environ.get("LASTPROG_DATA_DIR")
    if data_dir:
        base = Path(data_dir).resolve()
        paths.update(raw=base / "raw", store=base / "store", models=base / "models")
    mode = os.environ.get("LASTPROG_MODE", "full")
    if mode not in ("full", "demo"):
        raise ValueError(f"LASTPROG_MODE must be 'full' or 'demo', got {mode!r}")
    return Settings(
        root=root,
        data=data,
        issue_time_utc=raw["issue"]["time_utc"],
        cutoff_rule=raw["issue"]["cutoff"],
        backtest=backtest,
        model=model,
        conformal=conformal,
        weather=weather,
        paths=PathsCfg(**paths),
        fixture_overrides=fx,
        mode=mode,
        offline=os.environ.get("LASTPROG_OFFLINE") == "1",
    )
