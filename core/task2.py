"""Задача 2: ABC/XYZ-классификация и оборачиваемость.

ABC — по суммарной выручке за период (пороги доли накопленной выручки).
XYZ — по коэффициенту вариации помесячной выручки (стабильность спроса).
Оборачиваемость и дни покрытия — из дневных остатков (`stock_daily`),
в единицах хранения SKU.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from core.db import SessionLocal
from core.models import Chamber, Sale, Sku, StockDaily

# пороги (доля накопленной выручки для A/B; остальное C)
ABC_A, ABC_B = 0.80, 0.95
# пороги коэффициента вариации для X/Y (выше — Z)
XYZ_X, XYZ_Y = 0.10, 0.25


def _xyz(cv: float | None) -> str:
    if cv is None:
        return "—"
    if cv <= XYZ_X:
        return "X"
    if cv <= XYZ_Y:
        return "Y"
    return "Z"


def load_assortment() -> pd.DataFrame:
    """Датафрейм по SKU: revenue/gp, ABC, CV, XYZ, оборачиваемость, дни
    покрытия, остатки. ABC/XYZ — по продажам; оборот — по дневным остаткам."""
    with SessionLocal() as session:
        chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
        skus = {x.id: x for x in session.scalars(select(Sku))}
        sales = session.scalars(select(Sale)).all()
        daily = session.scalars(select(StockDaily)).all()

    # --- продажи: ABC + XYZ ---
    sdf = pd.DataFrame(
        [{"sku_id": x.sku_id, "month": f"{x.period.year:04d}-{x.period.month:02d}",
          "revenue": x.revenue, "gp": x.gross_profit} for x in sales],
        columns=["sku_id", "month", "revenue", "gp"],
    )
    if sdf.empty:
        agg = pd.DataFrame(columns=["sku_id", "revenue", "gp", "abc", "cv", "xyz"])
    else:
        months = sorted(sdf["month"].unique())
        agg = sdf.groupby("sku_id").agg(
            revenue=("revenue", "sum"), gp=("gp", "sum")
        ).reset_index()
        # ABC: доля накопленной выручки
        agg = agg.sort_values("revenue", ascending=False).reset_index(drop=True)
        total = agg["revenue"].clip(lower=0).sum()
        cum = agg["revenue"].clip(lower=0).cumsum()
        agg["cum_share"] = cum / total if total else 0.0
        agg["abc"] = agg["cum_share"].apply(
            lambda s: "A" if s <= ABC_A else ("B" if s <= ABC_B else "C")
        )
        # XYZ с поправкой на сезон: сезонный индекс по календарному месяцу
        # (из совокупной выручки), затем CV десезонализованного ряда по
        # активному периоду SKU (от первой до последней продажи).
        month_total = sdf.groupby("month")["revenue"].sum()
        m2cal = {m: int(m[5:7]) for m in months}
        cal_groups: dict[int, list[float]] = {}
        for m in months:
            cal_groups.setdefault(m2cal[m], []).append(float(month_total.get(m, 0.0)))
        cal_avg = {c: sum(v) / len(v) for c, v in cal_groups.items()}
        mean_cal = (sum(cal_avg.values()) / len(cal_avg)) if cal_avg else 0.0
        seas = {c: (cal_avg[c] / mean_cal if mean_cal else 1.0) for c in cal_avg}
        factors = np.array([seas.get(m2cal[m], 1.0) or 1.0 for m in months])

        piv = sdf.pivot_table(index="sku_id", columns="month", values="revenue",
                              aggfunc="sum", fill_value=0.0).reindex(columns=months,
                                                                     fill_value=0.0)
        arr = piv.values
        cv_vals = []
        for i in range(arr.shape[0]):
            row = arr[i]
            nz = np.nonzero(row > 0)[0]
            if len(nz) < 2:
                cv_vals.append(np.nan)
                continue
            sl = slice(nz[0], nz[-1] + 1)
            des = row[sl] / factors[sl]
            mu = des.mean()
            cv_vals.append(des.std() / mu if mu > 0 else np.nan)
        cvdf = pd.DataFrame({"sku_id": piv.index, "cv": cv_vals})
        agg = agg.merge(cvdf, on="sku_id", how="left")
        agg["xyz"] = agg["cv"].apply(lambda c: _xyz(None if pd.isna(c) else c))

    # --- дневные остатки: оборачиваемость, дни покрытия ---
    ddf = pd.DataFrame(
        [{"sku_id": st.sku_id, "day": st.day, "opening": st.opening,
          "closing": st.closing, "outbound": st.outbound} for st in daily],
        columns=["sku_id", "day", "opening", "closing", "outbound"],
    )
    if ddf.empty:
        inv = pd.DataFrame(columns=["sku_id", "avg_stock", "out_sum", "n_days",
                                    "current_stock", "turnover", "coverage_days"])
    else:
        ddf["avg_day"] = (ddf["opening"] + ddf["closing"]) / 2.0
        grp = ddf.groupby("sku_id")
        inv = grp.agg(avg_stock=("avg_day", "mean"), out_sum=("outbound", "sum"),
                      n_days=("day", "nunique")).reset_index()
        # текущий остаток = closing на последний день
        last = ddf.sort_values("day").groupby("sku_id").tail(1)[["sku_id", "closing"]]
        inv = inv.merge(last.rename(columns={"closing": "current_stock"}), on="sku_id")
        inv["turnover"] = (inv["out_sum"] / inv["avg_stock"]).where(inv["avg_stock"] > 0)
        avg_daily_out = inv["out_sum"] / inv["n_days"]
        inv["coverage_days"] = (inv["current_stock"] / avg_daily_out).where(avg_daily_out > 0)

    # --- объединяем + мета ---
    meta = pd.DataFrame([
        {"sku_id": sid, "code": x.code, "name": x.name,
         "group_kind": x.group_kind or "", "group2": (x.group_kind or "")[:2],
         "chamber": chambers.get(x.chamber_id, "—")}
        for sid, x in skus.items()
    ])
    df = meta.merge(agg, on="sku_id", how="left").merge(inv, on="sku_id", how="left")
    df["abc"] = df["abc"].fillna("—")
    df["xyz"] = df["xyz"].fillna("—")
    df["class"] = df["abc"] + df["xyz"]
    return df


def daily_period_days() -> int:
    """Сколько дней дневных остатков загружено (для подписей периода)."""
    with SessionLocal() as session:
        return session.scalar(select(func.count(func.distinct(StockDaily.day)))) or 0
