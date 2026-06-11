"""Кэширующие обёртки над расчётами `core/` для Dash.

Dash, в отличие от Streamlit, не перевыполняет скрипт — данные тянем по запросу
из callbacks. Чтобы не дёргать БД на каждый клик, держим простой TTL-кэш в
процессе (на сервере с gunicorn — per-worker, что нормально для внутреннего
инструмента).
"""

from __future__ import annotations

import time

import pandas as pd

from core.metrics import (
    chamber_occupancy_daily,
    chamber_snapshot,
    last_stock_date,
    load_chambers,
    load_facts,
)
from core.settings import get_setting
from core.task2 import daily_period_days, load_assortment

MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
             "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, fn, ttl: int = 600):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def _prepare() -> pd.DataFrame:
    df = load_facts()
    if df.empty:
        return df
    df["year"] = df["period"].dt.year
    df["mon"] = df["period"].dt.month
    df["mon_name"] = df["mon"].apply(
        lambda m: MONTHS_RU[int(m) - 1] if pd.notna(m) else ""
    )
    return df


def facts() -> pd.DataFrame:
    return _cached("facts", _prepare)


def chambers() -> pd.DataFrame:
    return _cached("chambers", load_chambers)


def last_date():
    return _cached("last_date", last_stock_date)


def snapshot(day):
    return _cached(f"snap:{day}", lambda: chamber_snapshot(day))


def assortment() -> pd.DataFrame:
    return _cached("assortment", load_assortment)


def occ_daily() -> pd.DataFrame:
    return _cached("occ_daily", chamber_occupancy_daily)


def days() -> int:
    return _cached("days", daily_period_days)


def scope() -> set[str]:
    return set((get_setting("scope_groups") or "").split(","))


def clear() -> None:
    _cache.clear()
