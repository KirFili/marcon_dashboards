"""Сводные метрики задачи 1: эффективность SKU (валовая прибыль против
занятых паллетомест) по месяцам.

Занятость месяца = среднее по дням месяца от паллетомест дня (нач+кон)/2.
Источник остатков — дневные ведомости (`stock_daily`).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select

from core.db import SessionLocal
from core.inventory import occupancy_slots
from core.models import Chamber, Sale, Sku, StockDaily
from core.sku_fields import build_ref as _ref


def load_facts() -> pd.DataFrame:
    """Датафрейм SKU×месяц: revenue, gross_profit, slots (занятость), мета.

    Занятость агрегируется из дневных остатков: паллетоместа считаются по
    каждому дню, затем усредняются по дням месяца; отгрузка — сумма по дням.
    """
    with SessionLocal() as session:
        chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
        skus = {s.id: s for s in session.scalars(select(Sku))}
        daily = session.scalars(select(StockDaily)).all()
        sales = session.scalars(select(Sale)).all()

    refs = {sid: _ref(s) for sid, s in skus.items()}

    drows = []
    for st in daily:
        avg = (st.opening + st.closing) / 2.0
        drows.append({
            "sku_id": st.sku_id,
            "month": f"{st.day.year:04d}-{st.day.month:02d}",
            "slots": occupancy_slots(refs[st.sku_id], avg),
            "outbound": st.outbound,
        })
    ddf = pd.DataFrame(drows, columns=["sku_id", "month", "slots", "outbound"])
    if not ddf.empty:
        ddf["slots"] = pd.to_numeric(ddf["slots"], errors="coerce")
        ddf["outbound"] = pd.to_numeric(ddf["outbound"], errors="coerce")
        occ = ddf.groupby(["sku_id", "month"]).agg(
            slots=("slots", "mean"), outbound=("outbound", "sum")
        ).reset_index()
    else:
        occ = pd.DataFrame(columns=["sku_id", "month", "slots", "outbound"])

    qdf = pd.DataFrame(
        [{"sku_id": x.sku_id, "month": f"{x.period.year:04d}-{x.period.month:02d}",
          "revenue": x.revenue, "gross_profit": x.gross_profit} for x in sales],
        columns=["sku_id", "month", "revenue", "gross_profit"],
    )
    df = pd.merge(occ, qdf, on=["sku_id", "month"], how="outer")

    meta = pd.DataFrame([
        {"sku_id": sid, "code": s.code, "name": s.name,
         "group_kind": s.group_kind or "", "group2": (s.group_kind or "")[:2],
         "chamber": chambers.get(s.chamber_id, "—")}
        for sid, s in skus.items()
    ])
    df = df.merge(meta, on="sku_id", how="left")
    df["period"] = pd.to_datetime(df["month"] + "-01")
    for col in ("revenue", "gross_profit", "slots", "outbound"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def chamber_occupancy_daily() -> pd.DataFrame:
    """Дневной ряд занятости камер: [day, chamber, slots] — суммарные
    паллетоместа по камере на каждый день (для тренда и прогноза переполнения).
    Паллетоместа считаются по среднему остатку дня (нач+кон)/2, как на странице
    товарооборота.
    """
    with SessionLocal() as session:
        chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
        skus = {s.id: s for s in session.scalars(select(Sku))}
        daily = session.scalars(select(StockDaily)).all()

    refs = {sid: _ref(s) for sid, s in skus.items()}
    rows = []
    for st in daily:
        slots = occupancy_slots(refs[st.sku_id], (st.opening + st.closing) / 2.0)
        if slots is None:
            continue
        rows.append({
            "day": st.day,
            "chamber": chambers.get(skus[st.sku_id].chamber_id, "—"),
            "slots": slots,
        })
    df = pd.DataFrame(rows, columns=["day", "chamber", "slots"])
    if df.empty:
        return df
    return df.groupby(["day", "chamber"], as_index=False)["slots"].sum()


def last_stock_date():
    """Последняя загруженная дата по дневным остаткам (или None, если пусто)."""
    with SessionLocal() as session:
        return session.scalar(select(func.max(StockDaily.day)))


def chamber_snapshot(day) -> pd.DataFrame:
    """Срез занятости на конкретную дату: по каждому SKU паллетоместа на `day`
    (по среднему остатку дня (нач+кон)/2, как и весь дашборд) плюс мета для
    фильтров: code, name, chamber, group_kind, group2.
    """
    with SessionLocal() as session:
        chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
        skus = {s.id: s for s in session.scalars(select(Sku))}
        daily = session.scalars(
            select(StockDaily).where(StockDaily.day == day)
        ).all()

    refs = {sid: _ref(s) for sid, s in skus.items()}
    rows = []
    for st in daily:
        s = skus[st.sku_id]
        slots = occupancy_slots(refs[st.sku_id], (st.opening + st.closing) / 2.0)
        rows.append({
            "code": s.code, "name": s.name,
            "chamber": chambers.get(s.chamber_id, "—"),
            "group_kind": s.group_kind or "", "group2": (s.group_kind or "")[:2],
            "slots": slots,
        })
    df = pd.DataFrame(
        rows, columns=["code", "name", "chamber", "group_kind", "group2", "slots"]
    )
    df["slots"] = pd.to_numeric(df["slots"], errors="coerce")
    return df


def load_chambers() -> pd.DataFrame:
    with SessionLocal() as session:
        rows = [
            {"chamber": c.name, "capacity": c.capacity_pallets, "sort": c.sort_order}
            for c in session.scalars(select(Chamber).order_by(Chamber.sort_order))
        ]
    return pd.DataFrame(rows)
