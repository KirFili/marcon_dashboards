from sqlalchemy import select

from core.db import SessionLocal
from core.models import Chamber, Setting

DEFAULT_SETTINGS: dict[str, tuple[str, str]] = {
    "pallet_tail_threshold_pct": ("10", "int"),
    "dead_window_days": ("90", "int"),
    "seasonal_baseline": ("year_over_year", "str"),
}

DEFAULT_CHAMBERS: list[tuple[str, float, int, int]] = [
    ("−18 №1", -18.0, 100, 1),
    ("−18 №2", -18.0, 100, 2),
    ("+5", 5.0, 50, 3),
]


def bootstrap_defaults() -> None:
    with SessionLocal() as session:
        if session.scalar(select(Chamber).limit(1)) is None:
            for name, temp, cap, order in DEFAULT_CHAMBERS:
                session.add(
                    Chamber(
                        name=name,
                        temperature_c=temp,
                        capacity_pallets=cap,
                        sort_order=order,
                        is_active=True,
                    )
                )
        for key, (value, vtype) in DEFAULT_SETTINGS.items():
            if session.get(Setting, key) is None:
                session.add(Setting(key=key, value=value, value_type=vtype))
        session.commit()


def _cast(value: str, vtype: str):
    if vtype == "int":
        return int(value)
    if vtype == "float":
        return float(value)
    if vtype == "bool":
        return value.lower() in {"1", "true", "yes"}
    return value


def get_setting(key: str):
    with SessionLocal() as session:
        s = session.get(Setting, key)
        return _cast(s.value, s.value_type) if s else None


def set_setting(key: str, value, vtype: str | None = None) -> None:
    with SessionLocal() as session:
        s = session.get(Setting, key)
        if s is None:
            session.add(Setting(key=key, value=str(value), value_type=vtype or "str"))
        else:
            s.value = str(value)
            if vtype:
                s.value_type = vtype
        session.commit()
