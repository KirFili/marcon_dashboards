"""Страница «Управление товарооборотом» на Dash.

Порт Streamlit-страницы `pages/2_Управление_товарооборотом.py`: те же расчёты
(через `core/`), но с явным состоянием, кросс-фильтрацией (клик по камере) и
нормальными таблицами (ag-grid). Все вкладки живут в layout статически, а
callbacks обновляют отдельные графики/таблицы — состояние контролов не сбрасывается.
"""

from __future__ import annotations

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, no_update

from core.fmt import money, num
from core.theme import BRAND, chamber_color_map
from dash_app import data
from dash_app.data import MONTHS_RU

# общие Inputs фильтров — повторяются во всех callbacks
_FILTERS = [
    Input("tv-only-profile", "value"),
    Input("tv-month-range", "value"),
    Input("tv-chambers", "value"),
    Input("tv-groups", "value"),
    Input("tv-refresh", "data"),
]


def _months(df: pd.DataFrame) -> list[str]:
    return sorted(df["month"].dropna().unique())


def _filtered(only_profile, mr, chambers_sel, groups_sel) -> pd.DataFrame:
    df = data.facts()
    months = _months(df)
    base = df[df["group2"].isin(data.scope())] if only_profile else df
    lo, hi = (mr or [0, len(months) - 1])
    m_from, m_to = months[lo], months[hi]
    f = base[(base["month"] >= m_from) & (base["month"] <= m_to)]
    if chambers_sel:
        f = f[f["chamber"].isin(chambers_sel)]
    if groups_sel:
        f = f[f["group_kind"].isin(groups_sel)]
    return f


# ---------------------------------------------------------------- layout
def layout():
    df = data.facts()
    if df.empty:
        return dbc.Alert("Нет данных. Загрузите справочник, продажи и остатки.",
                         color="info")

    months = _months(df)
    chambers_opts = sorted(df["chamber"].dropna().unique())
    groups_opts = sorted(df["group_kind"].dropna().unique())
    marks = {i: months[i] for i in range(0, len(months), max(1, len(months) // 6))}
    last = data.last_date()
    on_date_label = (
        f"Состояние складов на дату: {last.strftime('%d.%m.%Y')}" if last
        else "Состояние складов на дату"
    )

    # начальные значения считаем сразу (server-side) — чтобы данные были на любой
    # загрузке, не дожидаясь срабатывания callbacks на смонтированных компонентах
    d = (True, [0, len(months) - 1], [], [], 0)
    k_rev, k_gp, k_margin, k_slots, k_gpslot = _kpis(*d)
    dyn_rev, dyn_gp = _dynamics(*d)
    ch_fig, ch_tbl = _chambers(*d, False)
    rk_top, rk_bot, rk_rows, rk_cols = _ranking(*d)
    eff_fig = _efficiency(*d, True)
    seas_fig, seas_tbl = _seasonality(*d, "Валовая прибыль")

    controls = dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([dbc.Switch(id="tv-only-profile", label="Только профильные группы",
                            value=True)], md=3),
        dbc.Col([dbc.Label("Период (месяцы)"),
                 dcc.RangeSlider(id="tv-month-range", min=0, max=len(months) - 1,
                                 step=1, value=[0, len(months) - 1], marks=marks,
                                 tooltip={"placement": "bottom"})], md=5),
        dbc.Col([dbc.Label("Камеры"),
                 dcc.Dropdown(id="tv-chambers", options=chambers_opts, multi=True,
                              placeholder="Все")], md=2),
        dbc.Col([dbc.Label("Группы"),
                 dcc.Dropdown(id="tv-groups", options=groups_opts, multi=True,
                              placeholder="Все")], md=2),
        dbc.Col([dbc.Button("⟳ Обновить", id="tv-refresh-btn", color="secondary",
                            outline=True, size="sm", n_clicks=0,
                            className="mt-4")], md="auto"),
    ], className="g-2")), className="mb-3")

    def kpi(title, _id, value):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(title, className="text-muted small"),
            html.H4(value, id=_id, className="mb-0"),
        ])), md=True)

    kpis = dbc.Row([
        kpi("Выручка", "tv-kpi-rev", k_rev),
        kpi("Валовая прибыль", "tv-kpi-gp", k_gp),
        kpi("Маржа", "tv-kpi-margin", k_margin),
        kpi("Ср. занято/мес", "tv-kpi-slots", k_slots),
        kpi("ВП на паллетоместо", "tv-kpi-gpslot", k_gpslot),
    ], className="mb-3 g-2")

    tabs = dbc.Tabs([
        dbc.Tab(html.Div([dcc.Graph(id="tv-dyn-rev", figure=dyn_rev),
                          dcc.Graph(id="tv-dyn-gpslot", figure=dyn_gp)],
                         className="pt-3"), label="Динамика"),
        dbc.Tab(html.Div([
            dbc.Switch(id="tv-on-date", label=on_date_label, value=False,
                       className="pt-3"),
            dcc.Graph(id="tv-chamber-graph", figure=ch_fig),
            html.Div(ch_tbl, id="tv-chamber-table"),
        ]), label="Камеры"),
        dbc.Tab(html.Div([
            dbc.Row([dbc.Col(dcc.Graph(id="tv-rank-top", figure=rk_top), md=6),
                     dbc.Col(dcc.Graph(id="tv-rank-bot", figure=rk_bot), md=6)]),
            html.P("ВП на паллетоместо = валовая прибыль за период ÷ паллето-месяцы "
                   "занятости.", className="text-muted small"),
            dag.AgGrid(id="tv-rank-grid", columnSize="sizeToFit",
                       rowData=rk_rows, columnDefs=rk_cols,
                       defaultColDef={"sortable": True, "filter": True,
                                      "resizable": True},
                       dashGridOptions={"pagination": True,
                                        "paginationPageSize": 20},
                       style={"height": 430}),
        ], className="pt-3"), label="Рейтинг SKU"),
        dbc.Tab(html.Div([
            dbc.Checkbox(id="tv-log-x", label="Логарифм по оси X", value=True,
                         className="pt-3"),
            dcc.Graph(id="tv-eff-scatter", figure=eff_fig),
        ]), label="Эффективность"),
        dbc.Tab(html.Div([
            dbc.RadioItems(id="tv-seas-metric",
                           options=["Валовая прибыль", "Выручка"],
                           value="Валовая прибыль", inline=True, className="pt-3"),
            dcc.Graph(id="tv-seas-line", figure=seas_fig),
            html.Div(seas_tbl, id="tv-seas-table"),
        ]), label="Сезонность"),
    ])

    return html.Div([
        dcc.Store(id="tv-refresh", data=0),
        html.H2("Управление товарооборотом"),
        html.P("Эффективность SKU: валовая прибыль против занятых паллетомест, "
               "по месяцам.", className="text-muted"),
        controls, kpis, tabs,
    ])


@callback(Output("tv-refresh", "data"), Input("tv-refresh-btn", "n_clicks"),
          prevent_initial_call=True)
def _refresh(n):
    data.clear()
    return n


# ---------------------------------------------------------------- KPI
@callback(
    Output("tv-kpi-rev", "children"), Output("tv-kpi-gp", "children"),
    Output("tv-kpi-margin", "children"), Output("tv-kpi-slots", "children"),
    Output("tv-kpi-gpslot", "children"), *_FILTERS,
)
def _kpis(only_profile, mr, chambers_sel, groups_sel, _r):
    f = _filtered(only_profile, mr, chambers_sel, groups_sel)
    if f.empty:
        return "—", "—", "—", "—", "—"
    rev, gp = f["revenue"].sum(), f["gross_profit"].sum()
    occ = f[f["slots"] > 0]
    slots_sum = occ["slots"].sum()
    gp_per_slot = occ["gross_profit"].sum() / slots_sum if slots_sum else 0
    mwo = occ.groupby("month")["slots"].sum()
    avg_slots = mwo.mean() if len(mwo) else 0
    return (
        money(rev, digits=3), money(gp, digits=3),
        f"{100 * gp / rev:.1f}%" if rev else "—",
        num(avg_slots, 0) + " мест", money(gp_per_slot, "/мес"),
    )


# ---------------------------------------------------------------- Динамика
@callback(Output("tv-dyn-rev", "figure"), Output("tv-dyn-gpslot", "figure"),
          *_FILTERS)
def _dynamics(only_profile, mr, chambers_sel, groups_sel, _r):
    f = _filtered(only_profile, mr, chambers_sel, groups_sel)
    by_m = f.groupby("month").agg(revenue=("revenue", "sum"),
                                  gross_profit=("gross_profit", "sum")).reset_index()
    fig = go.Figure()
    fig.add_bar(x=by_m["month"], y=by_m["revenue"], name="Выручка",
                marker_color=BRAND["secondary"])
    fig.add_bar(x=by_m["month"], y=by_m["gross_profit"], name="Валовая прибыль",
                marker_color=BRAND["primary"])
    fig.update_layout(barmode="group", title="Выручка и валовая прибыль по месяцам",
                      height=380, legend_orientation="h", margin=dict(t=50))

    occ_m = f[f["slots"] > 0].groupby("month").agg(
        gp=("gross_profit", "sum"), slots=("slots", "sum")).reset_index()
    occ_m["gp_per_slot"] = occ_m["gp"] / occ_m["slots"]
    fig2 = px.line(occ_m, x="month", y="gp_per_slot", markers=True,
                   title="Валовая прибыль на паллетоместо по месяцам (₽/место)")
    fig2.update_layout(height=340, margin=dict(t=50))
    fig2.update_traces(line_color=BRAND["primary"])
    return fig, fig2


# ---------------------------------------------------------------- Камеры
@callback(Output("tv-chamber-graph", "figure"), Output("tv-chamber-table", "children"),
          *_FILTERS, Input("tv-on-date", "value"))
def _chambers(only_profile, mr, chambers_sel, groups_sel, _r, on_date):
    cham = data.chambers()
    if on_date and data.last_date() is not None:
        snap = data.snapshot(data.last_date())
        s = snap[snap["group2"].isin(data.scope())] if only_profile else snap
        if chambers_sel:
            s = s[s["chamber"].isin(chambers_sel)]
        if groups_sel:
            s = s[s["group_kind"].isin(groups_sel)]
        occ_by_ch = s.groupby("chamber")["slots"].sum().reset_index(name="occupied")
        bar_name = "Занято на дату"
        title = (f"Загруженность камер на "
                 f"{data.last_date().strftime('%d.%m.%Y')} (паллетоместа)")
        occ_label = "Занято"
    else:
        f = _filtered(only_profile, mr, chambers_sel, groups_sel)
        occ_by_ch = (f[f["slots"] > 0].groupby(["chamber", "month"])["slots"].sum()
                     .groupby("chamber").mean().reset_index(name="occupied"))
        bar_name = "Занято (ср/мес)"
        title = "Утилизация камер (паллетоместа)"
        occ_label = "Занято ср/мес"

    cap = cham.merge(occ_by_ch, on="chamber", how="left").fillna({"occupied": 0})
    cap["util"] = (100 * cap["occupied"] / cap["capacity"]).round(1)
    fig = go.Figure()
    fig.add_bar(x=cap["chamber"], y=cap["capacity"], name="Ёмкость",
                marker_color=BRAND["light"])
    fig.add_bar(x=cap["chamber"], y=cap["occupied"], name=bar_name,
                marker_color=BRAND["primary"])
    fig.update_layout(barmode="group", title=title, height=400,
                      legend_orientation="h", margin=dict(t=50))

    tbl = cap[["chamber", "capacity", "occupied", "util"]].copy()
    tbl["occupied"] = tbl["occupied"].round(0).astype(int)
    tbl.columns = ["Камера", "Ёмкость", occ_label, "Утилизация, %"]
    table = dbc.Table.from_dataframe(tbl, striped=True, bordered=False, hover=True,
                                     size="sm")
    return fig, table


@callback(Output("tv-chambers", "value"), Input("tv-chamber-graph", "clickData"),
          prevent_initial_call=True)
def _crossfilter_chamber(click):
    """Кросс-фильтр: клик по столбцу камеры → фильтр по этой камере."""
    if not click:
        return no_update
    return [click["points"][0]["x"]]


# ---------------------------------------------------------------- Рейтинг SKU
@callback(Output("tv-rank-top", "figure"), Output("tv-rank-bot", "figure"),
          Output("tv-rank-grid", "rowData"), Output("tv-rank-grid", "columnDefs"),
          *_FILTERS)
def _ranking(only_profile, mr, chambers_sel, groups_sel, _r):
    f = _filtered(only_profile, mr, chambers_sel, groups_sel)
    rank = f.groupby(["code", "name", "chamber"]).agg(
        gp=("gross_profit", "sum"), slot_months=("slots", "sum")).reset_index()
    rank = rank[rank["slot_months"] > 0].copy()
    rank["gp_per_slot"] = (rank["gp"] / rank["slot_months"]).round(0)
    rank = rank.sort_values("gp_per_slot", ascending=False)

    top = rank.head(15).sort_values("gp_per_slot")
    bot = rank.tail(15).sort_values("gp_per_slot")
    figt = px.bar(top, x="gp_per_slot", y="name", orientation="h",
                  title="Топ-15 по ВП/паллетоместо", height=450)
    figt.update_traces(marker_color=BRAND["primary"])
    figt.update_layout(margin=dict(t=50, l=10), yaxis_title="", xaxis_title="₽/место")
    figb = px.bar(bot, x="gp_per_slot", y="name", orientation="h",
                  title="Анти-топ-15 (паразиты места)", height=450)
    figb.update_traces(marker_color=BRAND["danger"])
    figb.update_layout(margin=dict(t=50, l=10), yaxis_title="", xaxis_title="₽/место")

    grid = rank.copy()
    grid["gp"] = grid["gp"].round(0)
    grid["slot_months"] = grid["slot_months"].round(1)
    cols = [
        {"field": "code", "headerName": "Код 1С", "maxWidth": 110},
        {"field": "name", "headerName": "Наименование", "flex": 2},
        {"field": "chamber", "headerName": "Камера"},
        {"field": "gp", "headerName": "Валовая прибыль, ₽",
         "valueFormatter": {"function": "d3.format(',.0f')(params.value)"}},
        {"field": "slot_months", "headerName": "Паллето-месяцы"},
        {"field": "gp_per_slot", "headerName": "ВП/паллетоместо, ₽",
         "valueFormatter": {"function": "d3.format(',.0f')(params.value)"}},
    ]
    return figt, figb, grid.to_dict("records"), cols


# ---------------------------------------------------------------- Эффективность
@callback(Output("tv-eff-scatter", "figure"), *_FILTERS, Input("tv-log-x", "value"))
def _efficiency(only_profile, mr, chambers_sel, groups_sel, _r, log_x):
    f = _filtered(only_profile, mr, chambers_sel, groups_sel)
    eff = f.groupby(["code", "name", "chamber"]).agg(
        gp=("gross_profit", "sum"), revenue=("revenue", "sum"),
        slot_months=("slots", "sum"), n=("month", "nunique")).reset_index()
    eff = eff[eff["slot_months"] > 0].copy()
    if eff.empty:
        return go.Figure()
    eff["avg_slots"] = (eff["slot_months"] / eff["n"]).round(1)
    eff["gp_per_slot"] = (eff["gp"] / eff["slot_months"]).round(0)
    eff["revenue"] = eff["revenue"].clip(lower=0)
    fig = px.scatter(
        eff, x="avg_slots", y="gp_per_slot", size="revenue", color="chamber",
        color_discrete_map=chamber_color_map(eff["chamber"].unique()),
        hover_name="name", log_x=bool(log_x), size_max=40, height=560,
        labels={"avg_slots": "Среднее занято паллетомест",
                "gp_per_slot": "ВП на паллетоместо, ₽", "chamber": "Камера",
                "revenue": "Выручка"})
    fig.update_layout(margin=dict(t=30), legend_orientation="h")
    return fig


# ---------------------------------------------------------------- Сезонность
@callback(Output("tv-seas-line", "figure"), Output("tv-seas-table", "children"),
          *_FILTERS, Input("tv-seas-metric", "value"))
def _seasonality(only_profile, mr, chambers_sel, groups_sel, _r, metric):
    f = _filtered(only_profile, mr, chambers_sel, groups_sel)
    col = "gross_profit" if metric == "Валовая прибыль" else "revenue"
    seas = f.groupby(["mon", "mon_name", "year"])[col].sum().reset_index()
    seas = seas.sort_values("mon")
    fig = px.line(seas, x="mon_name", y=col, color="year", markers=True, height=480,
                  category_orders={"mon_name": MONTHS_RU},
                  color_discrete_sequence=[BRAND["primary"], BRAND["accent"],
                                           BRAND["secondary"]],
                  labels={"mon_name": "Месяц", col: metric, "year": "Год"})
    fig.update_layout(margin=dict(t=30), legend_orientation="h")

    piv = seas.pivot_table(index="mon_name", columns="year", values=col,
                           aggfunc="sum").reindex(MONTHS_RU).dropna(how="all")
    years = sorted(seas["year"].unique())
    if len(years) >= 2 and years[-2] in piv and years[-1] in piv:
        y1, y2 = years[-2], years[-1]
        piv["Δ г/г, %"] = ((piv[y2] - piv[y1]) / piv[y1] * 100).round(1)
    piv = piv.reset_index().rename(columns={"mon_name": "Месяц"})
    piv.columns = [str(c) for c in piv.columns]
    table = dbc.Table.from_dataframe(piv, striped=True, hover=True, size="sm")
    return fig, table
