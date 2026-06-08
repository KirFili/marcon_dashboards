"""Задача 2: ABC/XYZ-классификация и оборачиваемость.

ABC — по суммарной выручке за период (пороги доли накопленной выручки).
XYZ — по коэффициенту вариации помесячной выручки (стабильность спроса).
Оборачиваемость и дни покрытия — из дневных остатков (`stock_daily`),
в единицах хранения SKU.
"""

from __future__ import annotations

from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from core.db import SessionLocal
from core.models import Chamber, Sale, Sku, StockDaily
from core.settings import get_setting


def _thresholds() -> tuple[float, float, float, float]:
    """Пороги ABC (A,B) и XYZ (X,Y) из настроек, в долях."""
    abc_a = (get_setting("abc_a_pct") or 80) / 100
    abc_b = (get_setting("abc_b_pct") or 95) / 100
    xyz_x = (get_setting("xyz_x_pct") or 10) / 100
    xyz_y = (get_setting("xyz_y_pct") or 25) / 100
    return abc_a, abc_b, xyz_x, xyz_y


def load_assortment() -> pd.DataFrame:
    """Датафрейм по SKU: revenue/gp, ABC, CV, XYZ, оборачиваемость, дни
    покрытия, остатки. ABC/XYZ — по продажам; оборот — по дневным остаткам."""
    abc_a, abc_b, xyz_x, xyz_y = _thresholds()
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
            lambda s: "A" if s <= abc_a else ("B" if s <= abc_b else "C")
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

        def _xyz(c):
            if pd.isna(c):
                return "—"
            return "X" if c <= xyz_x else ("Y" if c <= xyz_y else "Z")

        agg["xyz"] = agg["cv"].apply(_xyz)

    # --- дневные остатки: оборачиваемость, дни покрытия ---
    ddf = pd.DataFrame(
        [{"sku_id": st.sku_id, "day": st.day, "opening": st.opening,
          "closing": st.closing, "outbound": st.outbound} for st in daily],
        columns=["sku_id", "day", "opening", "closing", "outbound"],
    )
    if ddf.empty:
        inv = pd.DataFrame(columns=["sku_id", "avg_stock", "out_sum", "out_mean",
                                    "out_std", "n_days", "current_stock",
                                    "turnover", "coverage_days", "idle_days"])
    else:
        ddf["avg_day"] = (ddf["opening"] + ddf["closing"]) / 2.0
        grp = ddf.groupby("sku_id")
        inv = grp.agg(avg_stock=("avg_day", "mean"), out_sum=("outbound", "sum"),
                      out_mean=("outbound", "mean"), out_std=("outbound", "std"),
                      n_days=("day", "nunique")).reset_index()
        # текущий остаток = closing на последний день
        last = ddf.sort_values("day").groupby("sku_id").tail(1)[["sku_id", "closing"]]
        inv = inv.merge(last.rename(columns={"closing": "current_stock"}), on="sku_id")
        inv["turnover"] = (inv["out_sum"] / inv["avg_stock"]).where(inv["avg_stock"] > 0)
        avg_daily_out = inv["out_sum"] / inv["n_days"]
        inv["coverage_days"] = (inv["current_stock"] / avg_daily_out).where(avg_daily_out > 0)
        # дней простоя = с последней отгрузки (outbound>0) до последнего дня в БД
        max_day = ddf["day"].max()
        last_move = ddf[ddf["outbound"] > 0].groupby("sku_id")["day"].max()
        inv["idle_days"] = inv["sku_id"].map(
            lambda s: (max_day - last_move[s]).days if s in last_move.index else None
        )

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


def z_from_service_level(pct: float) -> float:
    """z-фактор (квантиль нормали) для целевого уровня сервиса в %.

    95% → ≈1.645. Ограничиваем (50%, 99.9%), чтобы не уйти в бесконечность.
    """
    p = min(max(pct / 100.0, 0.5), 0.999)
    return NormalDist().inv_cdf(p)


def compute_replenishment(df: pd.DataFrame, lead_time_days: int, z: float,
                          dead_window_days: int = 90) -> pd.DataFrame:
    """Добавляет к ассортименту страховой запас, точку заказа, рекомендацию.

    Спрос — дневная отгрузка из `stock_daily` (μ, σ за загруженный период).
    SS = z·σ·√L; точка заказа ROP = μ·L + SS; рекоменд. заказ = max(0, ROP − остаток).
    Статус: остаток ≤ μ·L → «Критично» (не доживёт до поставки),
    ≤ ROP → «Пора заказывать», иначе «OK».
    SKU без отгрузок дольше `dead_window_days` → «Неактивен» (не предлагаем заказ —
    скорее всего снят/распродан). «—» — нет дневной истории продаж.
    """
    d = df.copy()
    mu = d["out_mean"].fillna(0.0)
    sigma = d["out_std"].fillna(0.0)
    stock = d["current_stock"].fillna(0.0)
    idle = d["idle_days"]
    sqrt_l = float(lead_time_days) ** 0.5

    d["lead_demand"] = mu * lead_time_days
    d["safety_stock"] = z * sigma * sqrt_l
    d["reorder_point"] = d["lead_demand"] + d["safety_stock"]
    d["order_qty"] = (d["reorder_point"] - stock).clip(lower=0)

    has_demand = d["out_mean"].notna() & (mu > 0)
    dead = idle.notna() & (idle > dead_window_days)
    status = np.where(
        stock <= d["lead_demand"], "Критично",
        np.where(stock <= d["reorder_point"], "Пора заказывать", "OK"),
    )
    d["repl_status"] = np.where(
        has_demand, np.where(dead, "Неактивен", status), "—"
    )
    d.loc[d["repl_status"] == "Неактивен", "order_qty"] = 0.0
    return d


def seasonal_index() -> dict[int, float]:
    """Сезонный профиль: коэффициент спроса по календарному месяцу (1..12),
    нормированный к среднему = 1. Считается из совокупной выручки по месяцам
    (общий профиль по ассортименту — истории по отдельным SKU мало).
    """
    with SessionLocal() as session:
        sales = session.scalars(select(Sale)).all()
    if not sales:
        return {}
    sdf = pd.DataFrame(
        [{"month": f"{x.period.year:04d}-{x.period.month:02d}", "revenue": x.revenue}
         for x in sales]
    )
    month_total = sdf.groupby("month")["revenue"].sum()
    cal_groups: dict[int, list[float]] = {}
    for m, v in month_total.items():
        cal_groups.setdefault(int(m[5:7]), []).append(float(v))
    cal_avg = {c: sum(v) / len(v) for c, v in cal_groups.items()}
    mean_cal = (sum(cal_avg.values()) / len(cal_avg)) if cal_avg else 0.0
    return {c: (cal_avg[c] / mean_cal if mean_cal else 1.0) for c in cal_avg}


def forecast_seasonal_risk(df: pd.DataFrame, lead_time_days: int,
                           horizon_months: int = 8) -> tuple[pd.DataFrame, dict | None]:
    """Прогноз дефицита к ближайшему сезонному пику.

    Пик — месяц с максимальным сезонным коэффициентом в горизонте `horizon_months`
    вперёд от последнего дня данных. В пик дневной спрос ≈ μ·peak_factor, поэтому
    обычная точка заказа (рассчитанная на средний спрос) занижена. Считаем
    пиковую точку заказа peak_ROP = μ·peak_factor·L + страховой запас и
    предзаказ под пик = max(0, peak_ROP − остаток). Также — покрытие текущего
    остатка в днях при пиковом спросе. Требует колонку `safety_stock` (иначе 0).
    Возвращает df с колонками прогноза и инфо о пике (или None, если нет истории).
    """
    out = df.copy()
    cols = ["peak_daily", "peak_reorder_point", "preorder_qty", "coverage_at_peak"]
    for c in cols:
        out[c] = np.nan

    seas = seasonal_index()
    with SessionLocal() as session:
        last_day = session.scalar(select(func.max(StockDaily.day)))
    if not seas or last_day is None:
        return out, None

    # месяцы горизонта (с месяца после последнего дня данных)
    months: list[tuple[int, int]] = []
    for i in range(1, horizon_months + 1):
        idx = last_day.month - 1 + i
        months.append((last_day.year + idx // 12, idx % 12 + 1))
    peak_y, peak_m = max(months, key=lambda ym: seas.get(ym[1], 1.0))
    peak_factor = seas.get(peak_m, 1.0)
    days_to_peak = (date(peak_y, peak_m, 1) - last_day).days

    mu = out["out_mean"].fillna(0.0)
    stock = out["current_stock"].fillna(0.0)
    safety = out["safety_stock"].fillna(0.0) if "safety_stock" in out else 0.0
    peak_daily = mu * peak_factor
    out["peak_daily"] = peak_daily
    out["peak_reorder_point"] = peak_daily * lead_time_days + safety
    out["preorder_qty"] = (out["peak_reorder_point"] - stock).clip(lower=0)
    out["coverage_at_peak"] = (stock / peak_daily).where(peak_daily > 0)

    info = {
        "peak_label": f"{peak_y}-{peak_m:02d}",
        "peak_month": peak_m,
        "peak_factor": peak_factor,
        "days_to_peak": days_to_peak,
        "lead_time": lead_time_days,
        "last_day": last_day,
        "seas": seas,
    }
    return out, info


def daily_period_days() -> int:
    """Сколько дней дневных остатков загружено (для подписей периода)."""
    with SessionLocal() as session:
        return session.scalar(select(func.count(func.distinct(StockDaily.day)))) or 0
