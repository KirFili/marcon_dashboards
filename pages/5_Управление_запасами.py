import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.auth import require_password
from core.metrics import chamber_occupancy_daily, load_chambers
from core.settings import bootstrap_defaults, get_setting
from core.task2 import (
    compute_replenishment,
    daily_period_days,
    forecast_seasonal_risk,
    load_assortment,
    z_from_service_level,
)
from core.theme import ABC_COLORS, BRAND, REPL_EMOJI, chamber_color
from core.ui import table_filters

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


@st.cache_data(ttl=600)
def _occ_daily():
    return chamber_occupancy_daily()


@st.cache_data(ttl=600)
def _chambers():
    return load_chambers()


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
    chambers_sel = st.multiselect("Камеры", sorted(f["chamber"].dropna().unique()),
                                  default=[], placeholder="Выберите камеры")
if chambers_sel:
    f = f[f["chamber"].isin(chambers_sel)]

sold = f[f["abc"] != "—"].copy()

st.caption(f"Период дневных остатков: **{_days()} дн.**")
with st.expander("Как считается"):
    st.markdown(
        "- **XYZ** — с поправкой на сезон (CV десезонализованного ряда по активному "
        "периоду SKU). История пока ~1 год, по мере накопления данных классы уточнятся.\n"
        "- **Оборачиваемость и дни покрытия** — за загруженный период дневных остатков."
    )

# ---------- KPI ----------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Продаваемых SKU", len(sold))
k2.metric("Класс A", int((sold["abc"] == "A").sum()))
k3.metric("Класс B", int((sold["abc"] == "B").sum()))
k4.metric("Класс C", int((sold["abc"] == "C").sum()))
turn = f["turnover_days"].dropna()
k5.metric(
    "Медиана оборачиваемости, дн",
    f"{turn.median():.0f} дн" if len(turn) else "—",
    help=("Период оборота: сколько дней единица товара в среднем лежит на складе "
          "(средний остаток ÷ среднесуточная отгрузка). Меньше — лучше. "
          "Медиана по SKU устойчива к выбросам."),
)

# ---------- расчёт пополнения (общий для вкладок) ----------
lead_time = int(get_setting("lead_time_days") or 14)
service_level = int(get_setting("service_level_pct") or 95)
dead_window = int(get_setting("dead_window_days") or 90)
z = z_from_service_level(service_level)
rep = compute_replenishment(f, lead_time, z, dead_window)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "ABC / XYZ", "Оборачиваемость", "Пополнение",
    "Сезонный риск", "Переполнение камер"])

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
                      color_discrete_map=ABC_COLORS)
        figs.update_layout(height=360, margin=dict(t=50), showlegend=False)
        st.plotly_chart(figs, use_container_width=True)

    _abc_a = int(get_setting("abc_a_pct") or 80)
    _abc_b = int(get_setting("abc_b_pct") or 95)
    _xyz_x = int(get_setting("xyz_x_pct") or 10)
    _xyz_y = int(get_setting("xyz_y_pct") or 25)
    st.caption(f"A — топ по выручке (≤{_abc_a}% накопл.), B — ≤{_abc_b}%, C — хвост. "
               f"X — ровный спрос (CV≤{_xyz_x}%), Y — умеренно (≤{_xyz_y}%), "
               "Z — нерегулярный. «—» — мало истории. Пороги — в Настройках.")
    show = sold.sort_values("revenue", ascending=False)[[
        "code", "name", "chamber", "revenue", "abc", "cv", "xyz", "class",
        "turnover_days", "coverage_days", "current_stock"]]
    show = table_filters(show, key="abc", search_cols=("code", "name"),
                         cat_cols=("chamber", "abc", "xyz"))
    st.dataframe(
        show.rename(columns={
            "code": "Код 1С", "name": "Наименование", "chamber": "Камера",
            "revenue": "Выручка", "abc": "ABC", "cv": "CV", "xyz": "XYZ",
            "class": "Класс", "turnover_days": "Оборачиваемость, дн",
            "coverage_days": "Дни покрытия", "current_stock": "Остаток (ед.)"}),
        use_container_width=True, hide_index=True, height=420,
        column_config={
            "Выручка": st.column_config.NumberColumn(format="localized"),
            "CV": st.column_config.NumberColumn(format="%.2f"),
            "Оборачиваемость, дн": st.column_config.NumberColumn(
                format="%.0f", help="Период оборота в днях: средний остаток ÷ "
                "среднесуточная отгрузка. Меньше — лучше."),
            "Дни покрытия": st.column_config.NumberColumn(format="%.1f"),
            "Остаток (ед.)": st.column_config.NumberColumn(format="localized"),
        },
    )

# ---------- Оборачиваемость ----------
with tab2:
    inv = f[f["turnover_days"].notna()].copy()
    if inv.empty:
        st.info("Нет дневных остатков под текущие фильтры.")
    else:
        st.caption("Оборачиваемость в днях = средний остаток ÷ среднесуточная отгрузка — "
                   "сколько дней единица товара **в среднем лежит на складе** (меньше — лучше). "
                   "Дни покрытия = текущий остаток ÷ среднесуточная отгрузка.")
        figt = px.scatter(
            inv, x="coverage_days", y="turnover_days", color="abc", hover_name="name",
            hover_data={"code": True, "current_stock": ":,.0f"},
            category_orders={"abc": ["A", "B", "C", "—"]},
            color_discrete_map=ABC_COLORS,
            labels={"coverage_days": "Дни покрытия", "turnover_days": "Оборачиваемость, дн",
                    "abc": "ABC"},
            height=420,
        )
        figt.update_layout(margin=dict(t=30), legend_orientation="h")
        st.plotly_chart(figt, use_container_width=True)

        c1, c2 = st.columns(2)
        inv = inv.assign(turnover_days=inv["turnover_days"].round(0),
                         coverage_days=inv["coverage_days"].round(1),
                         current_stock=inv["current_stock"].round(0))
        slow = inv.sort_values("turnover_days", ascending=False).head(15)
        fast = inv.sort_values("turnover_days").head(15)
        _slowfast_cfg = {
            "Остаток": st.column_config.NumberColumn(format="localized"),
            "Оборот, дн": st.column_config.NumberColumn(
                format="%.0f", help="Период оборота в днях: средний остаток ÷ "
                "среднесуточная отгрузка."),
        }
        c1.markdown("**Залежавшиеся (долгий оборот)**")
        c1.dataframe(slow[["code", "name", "turnover_days", "coverage_days", "current_stock"]].rename(
            columns={"code": "Код", "name": "Наименование", "turnover_days": "Оборот, дн",
                     "coverage_days": "Дни покр.", "current_stock": "Остаток"}),
            use_container_width=True, hide_index=True, height=300, column_config=_slowfast_cfg)
        c2.markdown("**Быстрые (короткий оборот)**")
        c2.dataframe(fast[["code", "name", "turnover_days", "coverage_days", "current_stock"]].rename(
            columns={"code": "Код", "name": "Наименование", "turnover_days": "Оборот, дн",
                     "coverage_days": "Дни покр.", "current_stock": "Остаток"}),
            use_container_width=True, hide_index=True, height=300, column_config=_slowfast_cfg)

# ---------- Пополнение ----------
with tab3:
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
    show = table_filters(show, key="repl", search_cols=("code", "name"),
                         cat_cols=("chamber", "repl_status", "class"))

    if show.empty:
        st.success("Нет позиций, требующих заказа под текущие фильтры. 👌")
    else:
        cols = ["repl_status", "code", "name", "chamber", "class", "current_stock",
                "out_mean", "coverage_days", "safety_stock", "reorder_point",
                "order_qty", "idle_days"]
        disp = show[cols].copy()
        disp["repl_status"] = disp["repl_status"].map(
            lambda s: f"{REPL_EMOJI.get(s, '')} {s}".strip())
        st.dataframe(
            disp.rename(columns={
                "repl_status": "Статус", "code": "Код 1С", "name": "Наименование",
                "chamber": "Камера", "class": "Класс", "current_stock": "Остаток",
                "out_mean": "Спрос/сут", "coverage_days": "Дни покрытия",
                "safety_stock": "Страх. запас", "reorder_point": "Точка заказа",
                "order_qty": "Заказать (ед.)", "idle_days": "Простой, дн"}),
            use_container_width=True, hide_index=True, height=460,
            column_config={
                "Остаток": st.column_config.NumberColumn(format="localized"),
                "Спрос/сут": st.column_config.NumberColumn(format="%.2f"),
                "Дни покрытия": st.column_config.NumberColumn(format="%.1f"),
                "Страх. запас": st.column_config.NumberColumn(format="localized"),
                "Точка заказа": st.column_config.NumberColumn(format="localized"),
                "Заказать (ед.)": st.column_config.NumberColumn(format="localized"),
                "Простой, дн": st.column_config.NumberColumn(format="%.0f"),
            },
        )
        st.caption("«Заказать (ед.)» — сколько докинуть, чтобы вернуться к точке заказа "
                   "(минимум; объём партии/EOQ — отдельная задача). Единицы — в ед. хранения SKU.")

# ---------- Сезонный риск ----------
_MONTHS_RU = {1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май",
              6: "июнь", 7: "июль", 8: "август", 9: "сентябрь", 10: "октябрь",
              11: "ноябрь", 12: "декабрь"}

with tab4:
    fc, info = forecast_seasonal_risk(rep, lead_time)
    if info is None:
        st.info("Недостаточно данных для сезонного прогноза (нужны продажи и остатки).")
    else:
        peak_m = info["peak_month"]
        peak_year = int(info["peak_label"][:4])
        days_to_peak = info["days_to_peak"]
        order_in = max(0, days_to_peak - lead_time)
        st.caption(
            f"Ближайший сезонный пик — **{_MONTHS_RU[peak_m]} {peak_year}** "
            f"(спрос ×{info['peak_factor']:.2f} к среднему), через **{days_to_peak} дн.** "
            f"В пик дневной спрос выше, поэтому обычная точка заказа занижена: считаем "
            f"пиковую точку заказа = μ·×{info['peak_factor']:.2f}·{lead_time} + страховой запас. "
            f"Заказывать под пик — примерно через **{order_in} дн.** (за {lead_time} дн. до пика). "
            "Сезонный профиль — общий по ассортименту (истории по SKU мало)."
        )

        seas = info["seas"]
        prof_df = pd.DataFrame({
            "Месяц": [_MONTHS_RU[m] for m in range(1, 13)],
            "Коэффициент": [round(seas.get(m, 1.0), 2) for m in range(1, 13)],
            "is_peak": [m == peak_m for m in range(1, 13)],
        })
        figp = px.bar(prof_df, x="Месяц", y="Коэффициент",
                      color="is_peak",
                      color_discrete_map={True: BRAND["accent"], False: BRAND["secondary"]},
                      category_orders={"Месяц": [_MONTHS_RU[m] for m in range(1, 13)]},
                      title="Сезонный профиль спроса (1.0 = средний месяц)")
        figp.add_hline(y=1.0, line_dash="dot", line_color="#888")
        figp.update_layout(height=300, margin=dict(t=50), showlegend=False)
        st.plotly_chart(figp, use_container_width=True)

        live = fc[~fc["repl_status"].isin(["Неактивен", "—"])]
        need = live[live["preorder_qty"] > 0]
        new_peak = need[need["repl_status"] == "OK"]
        s1, s2, s3 = st.columns(3)
        s1.metric("Нужен запас под пик", len(need),
                  help="Остаток ниже пиковой точки заказа.")
        s2.metric("Из них «сейчас в норме»", len(new_peak),
                  help="По обычным правилам OK, но к пику запаса не хватит — спланировать закупку заранее.")
        s3.metric("Дней до пика", days_to_peak)

        only_new = st.checkbox(
            "Только «сейчас в норме, но к пику не хватит»", value=True)
        show = new_peak if only_new else need
        show = show.sort_values("preorder_qty", ascending=False)
        show = table_filters(show, key="seasonal", search_cols=("code", "name"),
                             cat_cols=("chamber", "class"))

        if show.empty:
            st.success("Нет позиций с сезонным риском под текущие фильтры. 👌")
        else:
            cols = ["code", "name", "chamber", "class", "current_stock", "out_mean",
                    "peak_daily", "coverage_at_peak", "reorder_point",
                    "peak_reorder_point", "preorder_qty"]
            st.dataframe(
                show[cols].rename(columns={
                    "code": "Код 1С", "name": "Наименование", "chamber": "Камера",
                    "class": "Класс", "current_stock": "Остаток", "out_mean": "Спрос/сут",
                    "peak_daily": "Спрос/сут в пик", "coverage_at_peak": "Покрытие в пик, дн",
                    "reorder_point": "Точка заказа", "peak_reorder_point": "Точка заказа (пик)",
                    "preorder_qty": "Предзаказ к пику (ед.)"}),
                use_container_width=True, hide_index=True, height=440,
                column_config={
                    "Остаток": st.column_config.NumberColumn(format="localized"),
                    "Спрос/сут": st.column_config.NumberColumn(format="%.2f"),
                    "Спрос/сут в пик": st.column_config.NumberColumn(format="%.2f"),
                    "Покрытие в пик, дн": st.column_config.NumberColumn(format="%.1f"),
                    "Точка заказа": st.column_config.NumberColumn(format="localized"),
                    "Точка заказа (пик)": st.column_config.NumberColumn(format="localized"),
                    "Предзаказ к пику (ед.)": st.column_config.NumberColumn(format="localized"),
                },
            )
            st.caption("«Предзаказ к пику» = пиковая точка заказа − текущий остаток. "
                       "Покрытие в пик — на сколько дней хватит текущего остатка при пиковом спросе.")

# ---------- Переполнение камер ----------
with tab5:
    occ = _occ_daily()
    cham = _chambers()
    if occ.empty:
        st.info("Нет дневных остатков для расчёта занятости камер.")
    else:
        window = st.select_slider("Окно тренда (последние дни)",
                                  options=[30, 60, 90, 120], value=60)
        st.caption(
            f"Занятость камер по дням (паллетоместа). Тренд — линейная аппроксимация по "
            f"последним **{window} дн.**, экстраполяция до ёмкости даёт «дней до переполнения». "
            "Наклон ≤ 0 — запас не растёт, переполнение не грозит."
        )
        capm = dict(zip(cham["chamber"], cham["capacity"]))
        rows = []
        fig = go.Figure()
        for ch in sorted(occ["chamber"].unique()):
            g = occ[occ["chamber"] == ch].sort_values("day")
            win = g.tail(window)
            y = win["slots"].to_numpy(dtype=float)
            cur = float(y[-1])
            cap = float(capm.get(ch, 0) or 0)
            slope = float(np.polyfit(np.arange(len(y)), y, 1)[0]) if len(y) >= 2 else 0.0
            if cap and cur >= cap:
                dtf, eta = 0.0, win["day"].iloc[-1]
            elif slope > 1e-6 and cap:
                dtf = (cap - cur) / slope
                eta = win["day"].iloc[-1] + pd.Timedelta(days=round(dtf))
            else:
                dtf, eta = None, None
            rows.append({
                "Камера": ch, "Занято": round(cur), "Ёмкость": int(cap),
                "Загрузка, %": round(100 * cur / cap, 1) if cap else None,
                "Наклон, мест/дн": round(slope, 2),
                "Дней до переполнения": round(dtf) if dtf is not None else None,
                "Прогноз даты": eta.strftime("%Y-%m-%d") if eta is not None else "—",
            })
            color = chamber_color(ch)
            fig.add_scatter(x=g["day"], y=g["slots"], name=ch, mode="lines",
                            line=dict(color=color))
            if cap:
                fig.add_hline(y=cap, line_dash="dash", line_color=color, opacity=0.5)
        fig.update_layout(height=380, margin=dict(t=30), legend_orientation="h",
                          yaxis_title="Паллетоместа", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Пунктир — ёмкость камеры. Сезонные колебания видны на ряду; "
                   "тренд считается только по выбранному окну.")

        summary = pd.DataFrame(rows)
        st.dataframe(
            summary, use_container_width=True, hide_index=True,
            column_config={
                "Загрузка, %": st.column_config.NumberColumn(format="%.1f"),
                "Наклон, мест/дн": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        warn = summary[summary["Дней до переполнения"].notna()
                       & (summary["Дней до переполнения"] <= 90)]
        if not warn.empty:
            for _, r in warn.iterrows():
                st.warning(f"⚠️ {r['Камера']}: при текущем тренде переполнение через "
                           f"~{int(r['Дней до переполнения'])} дн. ({r['Прогноз даты']}).")
