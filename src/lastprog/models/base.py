"""Shared types for the models: what one forecast origin sees."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..store import Store


@dataclass(frozen=True)
class OriginInput:
    origin: date  # issue day D
    target_day: date  # D + 1
    cutoff: pd.Timestamp  # observations strictly before this instant
    index: pd.DatetimeIndex  # hourly UTC instants of the target day
    features: pd.DataFrame  # build_features(store, target_day, cutoff, spec), indexed like `index`
    store: Store
