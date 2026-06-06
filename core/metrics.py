"""Сводные метрики задачи 1: эффективность SKU (валовая прибыль против
занятых паллетомест) по месяцам.

Занятость месяца = паллетоместа от среднего остатка (нач+кон)/2.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from core.db import SessionLocal
from core.inventory import occupancy_slots
from core.models import Chamber, Sale, Sku, Stock
from core.sku_fields import build_ref as _ref


def load_facts() -> pd.DataFrame:
    """Датафрейм SKU×месяц: revenue, gross_profit, slots (занятость), мета."""
    with SessionLocal() as session:
        chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
        skus = {s.id: s for s in session.scalars(select(Sku))}
        stock = session.scalars(select(Stock)).all()
        sales = session.scalars(select(Sale)).all()

    refs = {sid: _ref(s) for sid, s in skus.items()}

    srows = []
    for st in stock:
        avg = (st.opening + st.closing) / 2.0
        srows.append({
            "sku_id": st.sku_id, "period": st.period,
            "slots": occupancy_slots(refs[st.sku_id], avg),
            "outbound": st.outbound,
        })
    sdf = pd.DataFrame(srows, columns=["sku_id", "period", "slots", "outbound"])
    qdf = pd.DataFrame(
        [{"sku_id": x.sku_id, "period": x.period, "revenue": x.revenue,
          "gross_profit": x.gross_profit} for x in sales],
        columns=["sku_id", "period", "revenue", "gross_profit"],
    )
    df = pd.merge(sdf, qdf, on=["sku_id", "period"], how="outer")

    meta = pd.DataFrame([
        {"sku_id": sid, "code": s.code, "name": s.name,
         "group_kind": s.group_kind or "", "group2": (s.group_kind or "")[:2],
         "chamber": chambers.get(s.chamber_id, "—")}
        for sid, s in skus.items()
    ])
    df = df.merge(meta, on="sku_id", how="left")
    df["period"] = pd.to_datetime(df["period"])
    df["month"] = df["period"].dt.strftime("%Y-%m")
    for col in ("revenue", "gross_profit", "slots", "outbound"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_chambers() -> pd.DataFrame:
    with SessionLocal() as session:
        rows = [
            {"chamber": c.name, "capacity": c.capacity_pallets, "sort": c.sort_order}
            for c in session.scalars(select(Chamber).order_by(Chamber.sort_order))
        ]
    return pd.DataFrame(rows)
