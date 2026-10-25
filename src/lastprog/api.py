"""FastAPI app: /health, /forecast, /models. OpenAPI at /docs.

LASTPROG_MODE=demo serves the committed fixture period with the demo model (built by
`lastprog train --period fixtures`, offline); LASTPROG_MODE=full reads the store and <models>/LATEST under
LASTPROG_DATA_DIR (or the repository paths). In full mode the forecaster is rebuilt whenever the store
files, models/LATEST or the served manifest change on disk, so a refreshed store or a monthly refit is
picked up without a restart. /health answers 503 when the status is "degraded".
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from functools import cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .pipeline import load_store
from .service import BadRequest, DataNotReady, Forecaster, NoModel, UnknownModel


def models_root(settings: Settings) -> Path:
    return settings.paths.fixtures / "model" if settings.is_fixtures else settings.paths.models


def model_dir_for(settings: Settings) -> Path | None:
    """<root>/<version named in root/LATEST>, or None when no model has been trained."""
    root = models_root(settings)
    latest = root / "LATEST"
    if not latest.exists():
        return None
    return root / latest.read_text(encoding="utf-8").strip()


def build_forecaster(settings: Settings | None = None) -> Forecaster:
    settings = settings or load_settings()
    if settings.mode == "demo":
        settings = settings.for_fixtures()
    return Forecaster(settings, load_store(settings), model_dir_for(settings))


log = logging.getLogger(__name__)


def _effective(settings: Settings) -> Settings:
    return settings.for_fixtures() if settings.mode == "demo" else settings


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def state_signature(settings: Settings) -> tuple:
    """What the served state depends on: LATEST, the served manifest and (full mode) the store files."""
    s = _effective(settings)
    root = models_root(s)
    latest = root / "LATEST"
    version = latest.read_text(encoding="utf-8").strip() if latest.exists() else None
    sig = [s.mode, version, _stamp(latest)]
    if version:
        sig.append(_stamp(root / version / "manifest.json"))
    if s.mode == "full":
        sig += [_stamp(s.paths.store / "observations.parquet"), _stamp(s.paths.store / "weather.parquet")]
    return tuple(sig)


@cache
def _settings() -> Settings:
    return load_settings()


_lock = threading.Lock()
_current: tuple[tuple, Forecaster] | None = None


def get_forecaster() -> Forecaster:
    """The forecaster for the files as they are now; rebuilt when the store or the model changed on disk."""
    global _current
    settings = _settings()
    sig = state_signature(settings)
    with _lock:
        if _current is None or _current[0] != sig:
            try:
                _current = (sig, build_forecaster(settings))
            except Exception:
                if _current is None:
                    raise
                log.exception(
                    "rebuild after a change of the store or model failed; serving the previous state"
                )
        return _current[1]


ForecasterDep = Annotated[Forecaster, Depends(get_forecaster)]

app = FastAPI(
    title="Netzlast-Prognose",
    version="0.1.0",
    description="Probabilistic day-ahead forecasts of German hourly grid load. "
    "Data: Bundesnetzagentur | SMARD.de (CC BY 4.0).",
)


@app.get("/health")
def health(fc: ForecasterDep) -> JSONResponse:
    body = fc.health()
    return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)


@app.get("/models")
def models(fc: ForecasterDep) -> list[dict]:
    try:
        return fc.models()
    except NoModel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/forecast")
def forecast(
    fc: ForecasterDep,
    target_date: str | None = Query(None, description="Local target day YYYY-MM-DD; default: next local day"),
    model: str = Query("lgbm_cqr", description="lgbm_cqr or naive_week"),
) -> dict:
    try:
        day = date.fromisoformat(target_date) if target_date else fc.default_target()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid target_date {target_date!r}") from exc
    try:
        return fc.forecast(day, model)
    except UnknownModel as exc:
        raise HTTPException(status_code=404, detail=f"unknown model {model!r}") from exc
    except BadRequest as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DataNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoModel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
