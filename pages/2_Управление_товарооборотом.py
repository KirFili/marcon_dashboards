import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.auth import require_password
from core.fmt import money, num
from core.metrics import load_chambers, load_facts
from core.settings import bootstrap_defaults, get_setting
from core.theme import BRAND, chamber_color_map

st.set_page_config(page_title="Управление товарооборотом", page_icon="📦", layout="wide")
require_password()
bootstrap_defaults()

st.title("Управление товарооборотом")
st.caption("Эффективность SKU: валовая прибыль против занятых паллетомест, по месяцам.")


@st.cache_data(ttl=600)
def _facts():
    return load_facts()


@st.cache_data(ttl=600)
def _chambers():
    return load_chambers()


df = _facts()
if df.empty:
    st.info("Нет данных. Загрузите справочник, продажи и остатки.")
    st.stop()

df["year"] = df["period"].dt.year
df["mon"] = df["period"].dt.month
MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
df["mon_name"] = df["mon"].apply(lambda m: MONTHS_RU[int(m) - 1] if pd.notna(m) else "")

scope = set((get_setting("scope_groups") or "").split(","))
months = sorted(df["month"].dropna().unique())

# ---------- фильтры ----------
with st.sidebar:
    st.header("Фильтры")
    only_profile = st.checkbox("Только профильные группы", value=True)
    if len(months) > 1:
        m_from, m_to = st.select_slider(
            "Период (месяцы)", options=months, value=(months[0], months[-1])
        )
    else:
        m_from = m_to = months[0]
    base = df[df["group2"].isin(scope)] if only_profile else df
    chambers_sel = st.multiselect(
        "Камеры", sorted(base["chamber"].dropna().unique()), default=[]
    )
    groups_sel = st.multiselect(
        "Групировка по видам", sorted(base["group_kind"].dropna().unique()), default=[]
    )
    if st.button("Обновить данные"):
        st.cache_data.clear()
        st.rerun()

f = base[(base["month"] >= m_from) & (base["month"] <= m_to)]
if chambers_sel:
    f = f[f["chamber"].isin(chambers_sel)]
if groups_sel:
    f = f[f["group_kind"].isin(groups_sel)]

if f.empty:
    st.warning("Под фильтры ничего не попало.")
    st.stop()

# ---------- KPI ----------
rev = f["revenue"].sum()
gp = f["gross_profit"].sum()
# занятость и ВП/паллетоместо — только по месяцам, где есть остатки (иначе
# делёж/усреднение по «пустым» месяцам без дневных данных занижает числа)
occ = f[f["slots"] > 0]
slots_sum = occ["slots"].sum()
gp_per_slot = occ["gross_profit"].sum() / slots_sum if slots_sum else 0
months_with_occ = occ.groupby("month")["slots"].sum()
avg_slots = months_with_occ.mean() if len(months_with_occ) else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Выручка", money(rev, digits=3))
c2.metric("Валовая прибыль", money(gp, digits=3))
c3.metric("Маржа", f"{100*gp/rev:.1f}%" if rev else "—")
c4.metric("Ср. занято/мес", num(avg_slots, 0) + " мест")
c5.metric("ВП на паллетоместо", money(gp_per_slot, "/мес"))

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Динамика", "Камеры", "Рейтинг SKU", "Эффективность", "Сезонность"]
)

# ---------- Динамика ----------
with tab1:
    by_m = f.groupby("month").agg(
        revenue=("revenue", "sum"), gross_profit=("gross_profit", "sum")
    ).reset_index()
    fig = go.Figure()
    fig.add_bar(x=by_m["month"], y=by_m["revenue"], name="Выручка",
                marker_color=BRAND["secondary"])
    fig.add_bar(x=by_m["month"], y=by_m["gross_profit"], name="Валовая прибыль",
                marker_color=BRAND["primary"])
    fig.update_layout(barmode="group", title="Выручка и валовая прибыль по месяцам",
                      height=380, legend_orientation="h", margin=dict(t=50))
    st.plotly_chart(fig, use_container_width=True)

    occ_m = f[f["slots"] > 0].groupby("month").agg(
        gp=("gross_profit", "sum"), slots=("slots", "sum")
    ).reset_index()
    occ_m["gp_per_slot"] = occ_m["gp"] / occ_m["slots"]
    fig2 = px.line(occ_m, x="month", y="gp_per_slot", markers=True,
                   title="Валовая прибыль на паллетоместо по месяцам (₽/место)")
    fig2.update_layout(height=340, margin=dict(t=50))
    fig2.update_traces(line_color=BRAND["primary"])
    st.plotly_chart(fig2, use_container_width=True)

# ---------- Камеры ----------
with tab2:
    cham = _chambers()
    occ_by_ch = (
        f[f["slots"] > 0].groupby(["chamber", "month"])["slots"].sum()
        .groupby("chamber").mean().reset_index(name="avg_occupied")
    )
    cap = cham.merge(occ_by_ch, on="chamber", how="left").fillna({"avg_occupied": 0})
    cap["util"] = (100 * cap["avg_occupied"] / cap["capacity"]).round(1)
    fig3 = go.Figure()
    fig3.add_bar(x=cap["chamber"], y=cap["capacity"], name="Ёмкость",
                 marker_color=BRAND["light"])
    fig3.add_bar(x=cap["chamber"], y=cap["avg_occupied"], name="Занято (ср/мес)",
                 marker_color=BRAND["primary"])
    fig3.update_layout(barmode="group", title="Утилизация камер (паллетоместа)",
                       height=400, legend_orientation="h", margin=dict(t=50))
    st.plotly_chart(fig3, use_container_width=True)
    st.dataframe(
        cap[["chamber", "capacity", "avg_occupied", "util"]].rename(columns={
            "chamber": "Камера", "capacity": "Ёмкость",
            "avg_occupied": "Занято ср/мес", "util": "Утилизация, %"}),
        use_container_width=True, hide_index=True,
        column_config={
            "Занято ср/мес": st.column_config.NumberColumn(format="%.0f"),
            "Утилизация, %": st.column_config.NumberColumn(format="%.1f"),
        },
    )

# ---------- Рейтинг SKU ----------
with tab3:
    rank = f.groupby(["code", "name", "chamber"]).agg(
        gp=("gross_profit", "sum"), slot_months=("slots", "sum")
    ).reset_index()
    rank = rank[rank["slot_months"] > 0].copy()
    rank["gp_per_slot"] = (rank["gp"] / rank["slot_months"]).round(0)
    rank = rank.sort_values("gp_per_slot", ascending=False)

    st.caption("ВП на паллетоместо = валовая прибыль за период ÷ паллето-месяцы занятости.")
    colA, colB = st.columns(2)
    top = rank.head(15).sort_values("gp_per_slot")
    bot = rank.tail(15).sort_values("gp_per_slot")
    figt = px.bar(top, x="gp_per_slot", y="name", orientation="h",
                  title="Топ-15 по ВП/паллетоместо", height=450)
    figt.update_traces(marker_color=BRAND["primary"])
    figt.update_layout(margin=dict(t=50, l=10), yaxis_title="", xaxis_title="₽/место")
    colA.plotly_chart(figt, use_container_width=True)
    figb = px.bar(bot, x="gp_per_slot", y="name", orientation="h",
                  title="Анти-топ-15 (паразиты места)", height=450)
    figb.update_traces(marker_color=BRAND["danger"])
    figb.update_layout(margin=dict(t=50, l=10), yaxis_title="", xaxis_title="₽/место")
    colB.plotly_chart(figb, use_container_width=True)

    st.dataframe(
        rank.rename(columns={
            "code": "Код 1С", "name": "Наименование", "chamber": "Камера",
            "gp": "Валовая прибыль, ₽", "slot_months": "Паллето-месяцы",
            "gp_per_slot": "ВП/паллетоместо, ₽"}),
        use_container_width=True, hide_index=True, height=400,
        column_config={
            "Валовая прибыль, ₽": st.column_config.NumberColumn(format="localized"),
            "Паллето-месяцы": st.column_config.NumberColumn(format="localized"),
            "ВП/паллетоместо, ₽": st.column_config.NumberColumn(format="localized"),
        },
    )

# ---------- Эффективность (scatter) ----------
with tab4:
    st.caption(
        "Каждая точка — SKU. По X — сколько места в среднем держит, по Y — "
        "сколько валовой прибыли приносит одно паллетоместо. Правый-нижний угол "
        "(много места, низкая отдача) — кандидаты на сокращение."
    )
    eff = f.groupby(["code", "name", "chamber"]).agg(
        gp=("gross_profit", "sum"), revenue=("revenue", "sum"),
        slot_months=("slots", "sum"), n=("month", "nunique"),
    ).reset_index()
    eff = eff[eff["slot_months"] > 0].copy()
    eff["avg_slots"] = (eff["slot_months"] / eff["n"]).round(1)
    eff["gp_per_slot"] = (eff["gp"] / eff["slot_months"]).round(0)
    eff["revenue"] = eff["revenue"].clip(lower=0)
    if eff.empty:
        st.info("Нет данных по занятости под текущие фильтры.")
    else:
        log_x = st.checkbox("Логарифм по оси X (если разброс большой)", value=True)
        fig4 = px.scatter(
            eff, x="avg_slots", y="gp_per_slot", size="revenue", color="chamber",
            color_discrete_map=chamber_color_map(eff["chamber"].unique()),
            hover_name="name", hover_data={"code": True, "avg_slots": True,
                                           "gp_per_slot": ":,.0f", "revenue": ":,.0f"},
            log_x=log_x, size_max=40, height=560,
            labels={"avg_slots": "Среднее занято паллетомест",
                    "gp_per_slot": "ВП на паллетоместо, ₽", "chamber": "Камера",
                    "revenue": "Выручка"},
        )
        fig4.update_layout(margin=dict(t=30), legend_orientation="h")
        st.plotly_chart(fig4, use_container_width=True)

# ---------- Сезонность (год-к-году) ----------
with tab5:
    st.caption("Сравнение по календарным месяцам год-к-году. 2026 — частичный (по май).")
    metric = st.radio("Показатель", ["Валовая прибыль", "Выручка"], horizontal=True)
    col = "gross_profit" if metric == "Валовая прибыль" else "revenue"
    seas = f.groupby(["mon", "mon_name", "year"])[col].sum().reset_index()
    seas = seas.sort_values("mon")
    fig5 = px.line(
        seas, x="mon_name", y=col, color="year", markers=True, height=480,
        category_orders={"mon_name": MONTHS_RU},
        color_discrete_sequence=[BRAND["primary"], BRAND["accent"], BRAND["secondary"]],
        labels={"mon_name": "Месяц", col: metric, "year": "Год"},
    )
    fig5.update_layout(margin=dict(t=30), legend_orientation="h")
    st.plotly_chart(fig5, use_container_width=True)

    piv = seas.pivot_table(index="mon_name", columns="year", values=col,
                           aggfunc="sum").reindex(MONTHS_RU).dropna(how="all")
    years = sorted(seas["year"].unique())
    if len(years) >= 2:
        y1, y2 = years[-2], years[-1]
        if y1 in piv and y2 in piv:
            piv["Δ г/г, %"] = ((piv[y2] - piv[y1]) / piv[y1] * 100).round(1)
    st.dataframe(piv, use_container_width=True)
