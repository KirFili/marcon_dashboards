import pandas as pd
import plotly.express as px
import streamlit as st

from core.auth import require_password
from core.settings import bootstrap_defaults, get_setting
from core.task2 import (
    compute_replenishment,
    daily_period_days,
    load_assortment,
    z_from_service_level,
)

st.set_page_config(page_title="Управление запасами", page_icon="🧮", layout="wide")
require_password()
bootstrap_defaults()

st.title("Управление запасами")
st.caption("ABC/XYZ-классификация ассортимента и оборачиваемость (задача 2).")


@st.cache_data(ttl=600)
def _data():
    return load_assortment()


@st.cache_data(ttl=600)
def _days():
    return daily_period_days()


df = _data()
if df.empty:
    st.info("Нет данных. Загрузите справочник, продажи и дневные остатки.")
    st.stop()

scope = set((get_setting("scope_groups") or "").split(","))

# ---------- фильтры ----------
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    only_profile = st.checkbox("Только профильные", value=True)
with c2:
    if st.button("Обновить данные"):
        st.cache_data.clear()
        st.rerun()
f = df[df["group2"].isin(scope)] if only_profile else df
with c3:
    chambers_sel = st.multiselect("Камеры", sorted(f["chamber"].dropna().unique()), default=[])
if chambers_sel:
    f = f[f["chamber"].isin(chambers_sel)]

sold = f[f["abc"] != "—"].copy()

st.info(
    "XYZ — с поправкой на сезон (CV десезонализованного ряда по активному периоду SKU). "
    "История пока ~1 год, по мере накопления данных классы уточнятся. "
    f"Оборачиваемость и дни покрытия — за загруженный период дневных остатков (**{_days()} дн.**)."
)

# ---------- KPI ----------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Продаваемых SKU", len(sold))
k2.metric("Класс A", int((sold["abc"] == "A").sum()))
k3.metric("Класс B", int((sold["abc"] == "B").sum()))
k4.metric("Класс C", int((sold["abc"] == "C").sum()))
turn = f["turnover"].dropna()
k5.metric("Медиана оборачиваемости", f"{turn.median():.1f}" if len(turn) else "—")

tab1, tab2, tab3 = st.tabs(["ABC / XYZ", "Оборачиваемость", "Пополнение"])

# ---------- ABC / XYZ ----------
with tab1:
    colA, colB = st.columns([1, 1])
    with colA:
        mat = pd.crosstab(sold["abc"], sold["xyz"]).reindex(
            index=["A", "B", "C"], columns=["X", "Y", "Z", "—"], fill_value=0
        )
        fig = px.imshow(mat, text_auto=True, color_continuous_scale="Blues",
                        labels=dict(x="XYZ (стабильность)", y="ABC (вклад)", color="SKU"),
                        title="Матрица ABC×XYZ (кол-во SKU)", aspect="auto")
        fig.update_layout(height=360, margin=dict(t=50), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    with colB:
        share = sold.groupby("abc")["revenue"].sum().reindex(["A", "B", "C"]).fillna(0)
        figs = px.bar(share.reset_index(), x="abc", y="revenue", title="Выручка по классам ABC",
                      labels={"abc": "Класс", "revenue": "Выручка"}, color="abc",
                      color_discrete_map={"A": "#1F4E78", "B": "#6A9FB5", "C": "#C9D6DF"})
        figs.update_layout(height=360, margin=dict(t=50), showlegend=False)
        st.plotly_chart(figs, use_container_width=True)

    st.caption("A — топ по выручке (≤80% накопл.), B — ≤95%, C — хвост. "
               "X — ровный спрос, Y — умеренно, Z — нерегулярный. «—» — мало истории.")
    show = sold.sort_values("revenue", ascending=False)[[
        "code", "name", "chamber", "revenue", "abc", "cv", "xyz", "class",
        "turnover", "coverage_days", "current_stock"]]
    st.dataframe(
        show.rename(columns={
            "code": "Код 1С", "name": "Наименование", "chamber": "Камера",
            "revenue": "Выручка", "abc": "ABC", "cv": "CV", "xyz": "XYZ",
            "class": "Класс", "turnover": "Оборачиваемость",
            "coverage_days": "Дни покрытия", "current_stock": "Остаток (ед.)"}),
        use_container_width=True, hide_index=True, height=420,
        column_config={
            "Выручка": st.column_config.NumberColumn(format="%.0f"),
            "CV": st.column_config.NumberColumn(format="%.2f"),
            "Оборачиваемость": st.column_config.NumberColumn(format="%.1f"),
            "Дни покрытия": st.column_config.NumberColumn(format="%.1f"),
        },
    )

# ---------- Оборачиваемость ----------
with tab2:
    inv = f[f["turnover"].notna()].copy()
    if inv.empty:
        st.info("Нет дневных остатков под текущие фильтры.")
    else:
        st.caption("Оборачиваемость = отгрузка ÷ средний остаток за период (в ед. хранения). "
                   "Дни покрытия = текущий остаток ÷ среднесуточная отгрузка.")
        figt = px.scatter(
            inv, x="coverage_days", y="turnover", color="abc", hover_name="name",
            hover_data={"code": True, "current_stock": ":,.0f"},
            category_orders={"abc": ["A", "B", "C", "—"]},
            color_discrete_map={"A": "#1F4E78", "B": "#6A9FB5", "C": "#C9D6DF", "—": "#E0A458"},
            labels={"coverage_days": "Дни покрытия", "turnover": "Оборачиваемость", "abc": "ABC"},
            height=420,
        )
        figt.update_layout(margin=dict(t=30), legend_orientation="h")
        st.plotly_chart(figt, use_container_width=True)

        c1, c2 = st.columns(2)
        inv = inv.assign(turnover=inv["turnover"].round(1),
                         coverage_days=inv["coverage_days"].round(1),
                         current_stock=inv["current_stock"].round(0))
        slow = inv.sort_values("turnover").head(15)
        fast = inv.sort_values("turnover", ascending=False).head(15)
        c1.markdown("**Залежавшиеся (низкая оборачиваемость)**")
        c1.dataframe(slow[["code", "name", "turnover", "coverage_days", "current_stock"]].rename(
            columns={"code": "Код", "name": "Наименование", "turnover": "Обор.",
                     "coverage_days": "Дни покр.", "current_stock": "Остаток"}),
            use_container_width=True, hide_index=True, height=300)
        c2.markdown("**Быстрые (высокая оборачиваемость)**")
        c2.dataframe(fast[["code", "name", "turnover", "coverage_days", "current_stock"]].rename(
            columns={"code": "Код", "name": "Наименование", "turnover": "Обор.",
                     "coverage_days": "Дни покр.", "current_stock": "Остаток"}),
            use_container_width=True, hide_index=True, height=300)

# ---------- Пополнение ----------
with tab3:
    lead_time = int(get_setting("lead_time_days") or 14)
    service_level = int(get_setting("service_level_pct") or 95)
    dead_window = int(get_setting("dead_window_days") or 90)
    z = z_from_service_level(service_level)
    rep = compute_replenishment(f, lead_time, z, dead_window)

    st.caption(
        f"Срок поставки **{lead_time} дн.**, уровень сервиса **{service_level}%** (z={z:.2f}). "
        "Точка заказа = μ·L + страховой запас; страховой запас = z·σ·√L "
        "(μ, σ — среднесуточная отгрузка и её разброс). "
        f"SKU без отгрузок дольше **{dead_window} дн.** помечены «Неактивен». "
        "Параметры — в [Настройках](Настройки)."
    )

    order = {"Критично": 0, "Пора заказывать": 1, "OK": 2, "Неактивен": 3, "—": 4}
    rep = rep.assign(_ord=rep["repl_status"].map(order).fillna(5))
    live = rep[rep["repl_status"].isin(["Критично", "Пора заказывать", "OK"])]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Критично", int((rep["repl_status"] == "Критично").sum()),
              help="Остатка не хватит до прихода поставки.")
    k2.metric("🟠 Пора заказывать", int((rep["repl_status"] == "Пора заказывать").sum()),
              help="Остаток опустился ниже точки заказа.")
    k3.metric("🟢 В норме", int((rep["repl_status"] == "OK").sum()))
    k4.metric("⚪ Неактивных", int((rep["repl_status"] == "Неактивен").sum()),
              help=f"Нет отгрузок дольше {dead_window} дн. — вероятно сняты с продажи.")

    only_action = st.checkbox(
        "Только требующие заказа (критично + пора заказывать)", value=True)
    show = rep[rep["repl_status"].isin(["Критично", "Пора заказывать"])] if only_action \
        else live
    show = show.sort_values(["_ord", "coverage_days"])

    if show.empty:
        st.success("Нет позиций, требующих заказа под текущие фильтры. 👌")
    else:
        cols = ["repl_status", "code", "name", "chamber", "class", "current_stock",
                "out_mean", "coverage_days", "safety_stock", "reorder_point",
                "order_qty", "idle_days"]
        st.dataframe(
            show[cols].rename(columns={
                "repl_status": "Статус", "code": "Код 1С", "name": "Наименование",
                "chamber": "Камера", "class": "Класс", "current_stock": "Остаток",
                "out_mean": "Спрос/сут", "coverage_days": "Дни покрытия",
                "safety_stock": "Страх. запас", "reorder_point": "Точка заказа",
                "order_qty": "Заказать (ед.)", "idle_days": "Простой, дн"}),
            use_container_width=True, hide_index=True, height=460,
            column_config={
                "Остаток": st.column_config.NumberColumn(format="%.0f"),
                "Спрос/сут": st.column_config.NumberColumn(format="%.2f"),
                "Дни покрытия": st.column_config.NumberColumn(format="%.1f"),
                "Страх. запас": st.column_config.NumberColumn(format="%.0f"),
                "Точка заказа": st.column_config.NumberColumn(format="%.0f"),
                "Заказать (ед.)": st.column_config.NumberColumn(format="%.0f"),
                "Простой, дн": st.column_config.NumberColumn(format="%.0f"),
            },
        )
        st.caption("«Заказать (ед.)» — сколько докинуть, чтобы вернуться к точке заказа "
                   "(минимум; объём партии/EOQ — отдельная задача). Единицы — в ед. хранения SKU.")
