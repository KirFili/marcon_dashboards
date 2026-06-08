"""Единая фирменная палитра Маркона для графиков и подписей.

Один источник цвета на весь дашборд: убирает разнобой синих оттенков и
закрепляет семантику (оранжевый = риск/внимание, серый = нет данных).
"""

from __future__ import annotations

# Базовые цвета бренда
BRAND = {
    "primary": "#1F4E78",    # основной синий — главный ряд (ВП, «занято», класс A)
    "secondary": "#6A9FB5",  # средний синий — второй ряд (выручка-фон, класс B)
    "light": "#C9D6DF",      # светлый — фон/ёмкость/класс C
    "accent": "#E0A458",     # оранжевый — ВНИМАНИЕ/пик/риск (только один смысл!)
    "danger": "#C1666B",     # красно-кирпичный — анти-топ/критично/превышение
    "ok": "#4C9A6B",         # зелёный — в норме/OK
    "neutral": "#7A8896",    # серый — «нет данных», класс «—»
}

# ABC-классы
ABC_COLORS = {"A": BRAND["primary"], "B": BRAND["secondary"],
              "C": BRAND["light"], "—": BRAND["neutral"]}

# Статусы пополнения — синхронно с эмодзи в KPI
REPL_COLORS = {
    "Критично": BRAND["danger"],
    "Пора заказывать": BRAND["accent"],
    "OK": BRAND["ok"],
    "Неактивен": BRAND["neutral"],
}

REPL_EMOJI = {
    "Критично": "🔴",
    "Пора заказывать": "🟠",
    "OK": "🟢",
    "Неактивен": "⚪",
    "—": "",
}

# Камеры — единый источник; матчим по подстроке имени, чтобы переименование
# в Настройках не ломало цвет.
_CHAMBER_BASE = {
    "заморозка сд": BRAND["primary"],
    "заморозка тп": BRAND["secondary"],
    "охлажд": BRAND["accent"],
}


def chamber_color(name: str) -> str:
    low = (name or "").lower()
    for key, color in _CHAMBER_BASE.items():
        if key in low:
            return color
    return BRAND["neutral"]


def chamber_color_map(names) -> dict[str, str]:
    """{имя_камеры: цвет} для color_discrete_map в Plotly."""
    return {n: chamber_color(n) for n in names}
