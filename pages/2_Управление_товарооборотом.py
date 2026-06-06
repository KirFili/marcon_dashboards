import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.auth import require_password
from core.metrics import load_chambers, load_facts
from core.settings import bootstrap_defaults, get_setting

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
occ = f[f["slots"] > 0]
gp_per_slot = gp / occ["slots"].sum() if occ["slots"].sum() else 0
avg_slots = f.groupby("month")["slots"].sum().mean()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Выручка", f"{rev/1e6:,.1f} млн ₽")
c2.metric("Валовая прибыль", f"{gp/1e6:,.1f} млн ₽")
c3.metric("Маржа", f"{100*gp/rev:.1f}%" if rev else "—")
c4.metric("Ср. занято/мес", f"{avg_slots:,.0f} мест")
c5.metric("ВП на паллетоместо", f"{gp_per_slot:,.0f} ₽/мес")

tab1, tab2, tab3 = st.tabs(["Динамика", "Камеры", "Рейтинг SKU"])

# ---------- Динамика ----------
with tab1:
    by_m = f.groupby("month").agg(
        revenue=("revenue", "sum"), gross_profit=("gross_profit", "sum")
    ).reset_index()
    fig = go.Figure()
    fig.add_bar(x=by_m["month"], y=by_m["revenue"], name="Выручка", marker_color="#9DB4C0")
    fig.add_bar(x=by_m["month"], y=by_m["gross_profit"], name="Валовая прибыль",
                marker_color="#1F4E78")
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
    fig2.update_traces(line_color="#1F4E78")
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
    fig3.add_bar(x=cap["chamber"], y=cap["capacity"], name="Ёмкость", marker_color="#D9E2EC")
    fig3.add_bar(x=cap["chamber"], y=cap["avg_occupied"], name="Занято (ср/мес)",
                 marker_color="#1F4E78")
    fig3.update_layout(barmode="overlay", title="Утилизация камер (паллетоместа)",
                       height=400, legend_orientation="h", margin=dict(t=50))
    st.plotly_chart(fig3, use_container_width=True)
    st.dataframe(
        cap[["chamber", "capacity", "avg_occupied", "util"]].rename(columns={
            "chamber": "Камера", "capacity": "Ёмкость",
            "avg_occupied": "Занято ср/мес", "util": "Утилизация, %"}),
        use_container_width=True, hide_index=True,
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
    figt.update_traces(marker_color="#1F4E78")
    figt.update_layout(margin=dict(t=50, l=10), yaxis_title="", xaxis_title="₽/место")
    colA.plotly_chart(figt, use_container_width=True)
    figb = px.bar(bot, x="gp_per_slot", y="name", orientation="h",
                  title="Анти-топ-15 (паразиты места)", height=450)
    figb.update_traces(marker_color="#C1666B")
    figb.update_layout(margin=dict(t=50, l=10), yaxis_title="", xaxis_title="₽/место")
    colB.plotly_chart(figb, use_container_width=True)

    st.dataframe(
        rank.rename(columns={
            "code": "Код 1С", "name": "Наименование", "chamber": "Камера",
            "gp": "Валовая прибыль", "slot_months": "Паллето-месяцы",
            "gp_per_slot": "ВП/паллетоместо"}),
        use_container_width=True, hide_index=True, height=400,
    )
