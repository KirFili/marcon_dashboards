"""Компактное форматирование чисел для KPI (до десятых, влезает в карточки)."""

from __future__ import annotations

import math


def _nan(v) -> bool:
    try:
        return v is None or math.isnan(float(v))
    except (TypeError, ValueError):
        return v is None


def money(v, suffix: str = "", digits: int = 1) -> str:
    """Деньги компактно: млрд/млн/тыс ₽. digits — знаков после запятой.
    suffix напр. '/мес'."""
    if _nan(v):
        return "—"
    v = float(v)
    a = abs(v)
    if a >= 1e9:
        s = f"{v / 1e9:.{digits}f} млрд ₽"
    elif a >= 1e6:
        s = f"{v / 1e6:.{digits}f} млн ₽"
    elif a >= 1e3:
        s = f"{v / 1e3:.{digits}f} тыс ₽"
    else:
        s = f"{v:.0f} ₽"
    return s + suffix


def num(v, digits: int = 1) -> str:
    """Число до десятых (по умолчанию), с пробелом-разделителем тысяч."""
    if _nan(v):
        return "—"
    return f"{float(v):,.{digits}f}".replace(",", " ")
