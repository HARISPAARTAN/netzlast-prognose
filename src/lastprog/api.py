"""FastAPI app: /health, /forecast, /models. OpenAPI at /docs.

LASTPROG_MODE=demo serves the committed fixture period with the demo model (built by
`lastprog train --period fixtures`, offline); LASTPROG_MODE=full reads the store and <models>/LATEST under
LASTPROG_DATA_DIR (or the repository paths).
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

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


@lru_cache(maxsize=1)
def get_forecaster() -> Forecaster:
    return build_forecaster()


ForecasterDep = Annotated[Forecaster, Depends(get_forecaster)]

app = FastAPI(
    title="Netzlast-Prognose",
    version="0.1.0",
    description="Probabilistic day-ahead forecasts of German hourly grid load. "
    "Data: Bundesnetzagentur | SMARD.de (CC BY 4.0).",
)


@app.get("/health")
def health(fc: ForecasterDep) -> dict:
    return fc.health()


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
