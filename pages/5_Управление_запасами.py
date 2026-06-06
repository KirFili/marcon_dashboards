import pandas as pd
import plotly.express as px
import streamlit as st

from core.auth import require_password
from core.settings import bootstrap_defaults, get_setting
from core.task2 import daily_period_days, load_assortment

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

tab1, tab2 = st.tabs(["ABC / XYZ", "Оборачиваемость"])

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
