"""Страница «Управление запасами» на Dash (задача 2).

Порт `pages/5_Управление_запасами.py`: ABC/XYZ, оборачиваемость, пополнение,
сезонный риск, переполнение камер. Все расчёты — через `core.task2`/`core.metrics`.
"""

from __future__ import annotations

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from core.settings import get_setting
from core.task2 import (
    compute_replenishment,
    forecast_seasonal_risk,
    z_from_service_level,
)
from core.theme import ABC_COLORS, BRAND, REPL_EMOJI, chamber_color
from dash_app import data

_MONTHS_RU = {1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май",
              6: "июнь", 7: "июль", 8: "август", 9: "сентябрь", 10: "октябрь",
              11: "ноябрь", 12: "декабрь"}

_FILTERS = [
    Input("iv-only-profile", "value"),
    Input("iv-chambers", "value"),
    Input("iv-refresh", "data"),
]

_MONEY = {"function": "d3.format(',.0f')(params.value)"}


def _filtered(only_profile, chambers_sel) -> pd.DataFrame:
    df = data.assortment()
    f = df[df["group2"].isin(data.scope())] if only_profile else df
    if chambers_sel:
        f = f[f["chamber"].isin(chambers_sel)]
    return f


def _repl_params():
    lead = int(get_setting("lead_time_days") or 14)
    svc = int(get_setting("service_level_pct") or 95)
    dead = int(get_setting("dead_window_days") or 90)
    return lead, svc, dead, z_from_service_level(svc)


def _grid(_id, height=420, rowData=None, columnDefs=None):
    return dag.AgGrid(id=_id, columnSize="sizeToFit",
                      rowData=rowData or [], columnDefs=columnDefs or [],
                      defaultColDef={"sortable": True, "filter": True,
                                     "resizable": True},
                      dashGridOptions={"pagination": True, "paginationPageSize": 15},
                      style={"height": height})


# ---------------------------------------------------------------- layout
def layout():
    df = data.assortment()
    if df.empty:
        return dbc.Alert("Нет данных. Загрузите справочник, продажи и дневные "
                         "остатки.", color="info")
    chambers_opts = sorted(df["chamber"].dropna().unique())

    # начальные значения — сразу server-side, чтобы данные были на любой загрузке
    d = (True, [], 0)
    k_sold, k_a, k_b, k_c, k_turn = _kpis(*d)
    abc_m, abc_sh, abc_cap, abc_rows, abc_cols = _abc(*d)
    scat, slow_med, slow_rows, slow_cols, fast_med, fast_rows, fast_cols = \
        _turnover(*d, 15, 15)
    rp_cap, rp_crit, rp_order, rp_ok, rp_dead, rp_empty, rp_rows, rp_cols = \
        _replenishment(*d, True)
    se_cap, se_fig, se_need, se_new, se_days, se_empty, se_rows, se_cols = \
        _seasonal(*d, True)
    ov_cap, ov_fig, ov_tbl, ov_warn = _overflow(60, 0)

    controls = dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col(dbc.Switch(id="iv-only-profile", label="Только профильные",
                           value=True), md=3),
        dbc.Col([dbc.Label("Камеры"),
                 dcc.Dropdown(id="iv-chambers", options=chambers_opts, multi=True,
                              placeholder="Все")], md=6),
        dbc.Col(dbc.Button("⟳ Обновить", id="iv-refresh-btn", color="secondary",
                           outline=True, size="sm", className="mt-4"), md="auto"),
    ], className="g-2")), className="mb-3")

    def kpi(title, _id, value):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(title, className="text-muted small"),
            html.H4(value, id=_id, className="mb-0")])), md=True)

    kpis = dbc.Row([
        kpi("Продаваемых SKU", "iv-kpi-sold", k_sold), kpi("Класс A", "iv-kpi-a", k_a),
        kpi("Класс B", "iv-kpi-b", k_b), kpi("Класс C", "iv-kpi-c", k_c),
        kpi("Медиана оборачиваемости, дн", "iv-kpi-turn", k_turn),
    ], className="mb-3 g-2")

    tabs = dbc.Tabs([
        # --- ABC / XYZ ---
        dbc.Tab(html.Div([
            dbc.Row([dbc.Col(dcc.Graph(id="iv-abc-matrix", figure=abc_m), md=6),
                     dbc.Col(dcc.Graph(id="iv-abc-share", figure=abc_sh), md=6)]),
            html.P(abc_cap, id="iv-abc-caption", className="text-muted small"),
            _grid("iv-abc-grid", rowData=abc_rows, columnDefs=abc_cols),
        ], className="pt-3"), label="ABC / XYZ"),
        # --- Оборачиваемость ---
        dbc.Tab(html.Div([
            dcc.Graph(id="iv-turn-scatter", figure=scat),
            dbc.Row([
                dbc.Col([html.B("Залежавшиеся (долгий оборот)"),
                         dbc.Label("Сколько показать", className="mt-2"),
                         dbc.Input(id="iv-slow-n", type="number", value=15, min=1,
                                   step=1, size="sm", style={"width": "120px"}),
                         html.Div(slow_med, id="iv-slow-median", className="text-muted my-1"),
                         _grid("iv-slow-grid", height=320, rowData=slow_rows,
                               columnDefs=slow_cols)], md=6),
                dbc.Col([html.B("Быстрые (короткий оборот)"),
                         dbc.Label("Сколько показать", className="mt-2"),
                         dbc.Input(id="iv-fast-n", type="number", value=15, min=1,
                                   step=1, size="sm", style={"width": "120px"}),
                         html.Div(fast_med, id="iv-fast-median", className="text-muted my-1"),
                         _grid("iv-fast-grid", height=320, rowData=fast_rows,
                               columnDefs=fast_cols)], md=6),
            ]),
        ], className="pt-3"), label="Оборачиваемость"),
        # --- Пополнение ---
        dbc.Tab(html.Div([
            html.P(rp_cap, id="iv-repl-caption", className="text-muted small pt-2"),
            dbc.Row([kpi("🔴 Критично", "iv-repl-crit", rp_crit),
                     kpi("🟠 Пора заказывать", "iv-repl-order", rp_order),
                     kpi("🟢 В норме", "iv-repl-ok", rp_ok),
                     kpi("⚪ Неактивных", "iv-repl-dead", rp_dead)], className="mb-3 g-2"),
            dbc.Switch(id="iv-repl-action", value=True,
                       label="Только требующие заказа (критично + пора заказывать)"),
            html.Div(rp_empty, id="iv-repl-empty"),
            _grid("iv-repl-grid", height=460, rowData=rp_rows, columnDefs=rp_cols),
        ], className="pt-3"), label="Пополнение"),
        # --- Сезонный риск ---
        dbc.Tab(html.Div([
            html.P(se_cap, id="iv-seas-caption", className="text-muted small pt-2"),
            dcc.Graph(id="iv-seas-profile", figure=se_fig),
            dbc.Row([kpi("Нужен запас под пик", "iv-seas-need", se_need),
                     kpi("Из них «сейчас в норме»", "iv-seas-new", se_new),
                     kpi("Дней до пика", "iv-seas-days", se_days)], className="mb-3 g-2"),
            dbc.Switch(id="iv-seas-only-new", value=True,
                       label="Только «сейчас в норме, но к пику не хватит»"),
            html.Div(se_empty, id="iv-seas-empty"),
            _grid("iv-seas-grid", height=440, rowData=se_rows, columnDefs=se_cols),
        ], className="pt-3"), label="Сезонный риск"),
        # --- Переполнение камер ---
        dbc.Tab(html.Div([
            dbc.Label("Окно тренда (последние дни)", className="pt-2"),
            dcc.Slider(id="iv-overflow-window", min=30, max=120, step=None,
                       marks={30: "30", 60: "60", 90: "90", 120: "120"}, value=60),
            html.P(ov_cap, id="iv-overflow-caption", className="text-muted small"),
            dcc.Graph(id="iv-overflow-graph", figure=ov_fig),
            html.Div(ov_tbl, id="iv-overflow-table"),
            html.Div(ov_warn, id="iv-overflow-warn"),
        ], className="pt-3"), label="Переполнение камер"),
    ], active_tab="tab-0")  # явно активируем первую вкладку (иначе её панель скрыта)

    return html.Div([
        dcc.Store(id="iv-refresh", data=0),
        html.H2("Управление запасами"),
        html.P("ABC/XYZ-классификация ассортимента и оборачиваемость (задача 2). "
               f"Период дневных остатков: {data.days()} дн.",
               className="text-muted"),
        controls, kpis, tabs,
    ])


@callback(Output("iv-refresh", "data"), Input("iv-refresh-btn", "n_clicks"),
          prevent_initial_call=True)
def _refresh(n):
    data.clear()
    return n


# ---------------------------------------------------------------- KPI
@callback(Output("iv-kpi-sold", "children"), Output("iv-kpi-a", "children"),
          Output("iv-kpi-b", "children"), Output("iv-kpi-c", "children"),
          Output("iv-kpi-turn", "children"), *_FILTERS)
def _kpis(only_profile, chambers_sel, _r):
    f = _filtered(only_profile, chambers_sel)
    sold = f[f["abc"] != "—"]
    turn = f["turnover_days"].dropna()
    return (
        len(sold), int((sold["abc"] == "A").sum()), int((sold["abc"] == "B").sum()),
        int((sold["abc"] == "C").sum()),
        f"{turn.median():.0f} дн" if len(turn) else "—",
    )


# ---------------------------------------------------------------- ABC / XYZ
@callback(Output("iv-abc-matrix", "figure"), Output("iv-abc-share", "figure"),
          Output("iv-abc-caption", "children"),
          Output("iv-abc-grid", "rowData"), Output("iv-abc-grid", "columnDefs"),
          *_FILTERS)
def _abc(only_profile, chambers_sel, _r):
    f = _filtered(only_profile, chambers_sel)
    sold = f[f["abc"] != "—"].copy()
    mat = pd.crosstab(sold["abc"], sold["xyz"]).reindex(
        index=["A", "B", "C"], columns=["X", "Y", "Z", "—"], fill_value=0)
    fig = px.imshow(mat, text_auto=True, color_continuous_scale="Blues",
                    labels=dict(x="XYZ (стабильность)", y="ABC (вклад)", color="SKU"),
                    title="Матрица ABC×XYZ (кол-во SKU)", aspect="auto")
    fig.update_layout(height=360, margin=dict(t=50), coloraxis_showscale=False)

    share = sold.groupby("abc")["revenue"].sum().reindex(["A", "B", "C"]).fillna(0)
    figs = px.bar(share.reset_index(), x="abc", y="revenue",
                  title="Выручка по классам ABC", color="abc",
                  labels={"abc": "Класс", "revenue": "Выручка"},
                  color_discrete_map=ABC_COLORS)
    figs.update_layout(height=360, margin=dict(t=50), showlegend=False)

    a, b = int(get_setting("abc_a_pct") or 80), int(get_setting("abc_b_pct") or 95)
    x, y = int(get_setting("xyz_x_pct") or 10), int(get_setting("xyz_y_pct") or 25)
    cap = (f"A — топ по выручке (≤{a}% накопл.), B — ≤{b}%, C — хвост. "
           f"X — ровный спрос (CV≤{x}%), Y — ≤{y}%, Z — нерегулярный. "
           "«—» — мало истории. Пороги — в Настройках.")

    g = sold.sort_values("revenue", ascending=False).copy()
    g["revenue"] = g["revenue"].round(0)
    g["cv"] = g["cv"].round(2)
    g["turnover_days"] = g["turnover_days"].round(0)
    g["coverage_days"] = g["coverage_days"].round(1)
    g["current_stock"] = g["current_stock"].round(0)
    cols = [
        {"field": "code", "headerName": "Код 1С", "maxWidth": 110},
        {"field": "name", "headerName": "Наименование", "flex": 2},
        {"field": "chamber", "headerName": "Камера"},
        {"field": "revenue", "headerName": "Выручка", "valueFormatter": _MONEY},
        {"field": "abc", "headerName": "ABC", "maxWidth": 80},
        {"field": "cv", "headerName": "CV", "maxWidth": 90},
        {"field": "xyz", "headerName": "XYZ", "maxWidth": 80},
        {"field": "turnover_days", "headerName": "Оборач., дн"},
        {"field": "coverage_days", "headerName": "Дни покрытия"},
        {"field": "current_stock", "headerName": "Остаток", "valueFormatter": _MONEY},
    ]
    keep = ["code", "name", "chamber", "revenue", "abc", "cv", "xyz",
            "turnover_days", "coverage_days", "current_stock"]
    return fig, figs, cap, g[keep].to_dict("records"), cols


# ---------------------------------------------------------------- Оборачиваемость
@callback(Output("iv-turn-scatter", "figure"),
          Output("iv-slow-median", "children"), Output("iv-slow-grid", "rowData"),
          Output("iv-slow-grid", "columnDefs"),
          Output("iv-fast-median", "children"), Output("iv-fast-grid", "rowData"),
          Output("iv-fast-grid", "columnDefs"),
          *_FILTERS, Input("iv-slow-n", "value"), Input("iv-fast-n", "value"))
def _turnover(only_profile, chambers_sel, _r, slow_n, fast_n):
    f = _filtered(only_profile, chambers_sel)
    inv = f[f["turnover_days"].notna()].copy()
    if inv.empty:
        empty = go.Figure()
        return empty, "—", [], [], "—", [], []

    plot = inv.assign(turnover_days=inv["turnover_days"].clip(upper=365),
                      coverage_days=inv["coverage_days"].clip(upper=365))
    fig = px.scatter(plot, x="coverage_days", y="turnover_days", color="abc",
                     hover_name="name", category_orders={"abc": ["A", "B", "C", "—"]},
                     color_discrete_map=ABC_COLORS,
                     labels={"coverage_days": "Дни покрытия",
                             "turnover_days": "Оборачиваемость, дн", "abc": "ABC"},
                     height=420)
    fig.update_layout(margin=dict(t=30), legend_orientation="h")
    fig.update_yaxes(range=[-10, 380])
    fig.update_xaxes(range=[-10, 380])

    inv = inv.assign(turnover_days=inv["turnover_days"].round(0),
                     coverage_days=inv["coverage_days"].round(1),
                     current_stock=inv["current_stock"].round(0))
    cols = [
        {"field": "code", "headerName": "Код", "maxWidth": 110},
        {"field": "name", "headerName": "Наименование", "flex": 2},
        {"field": "turnover_days", "headerName": "Оборот, дн"},
        {"field": "coverage_days", "headerName": "Дни покр."},
        {"field": "current_stock", "headerName": "Остаток", "valueFormatter": _MONEY},
    ]
    keep = ["code", "name", "turnover_days", "coverage_days", "current_stock"]

    def _sub(ordered, n):
        sub = ordered.head(int(n or 15))
        med = (f"Медиана оборота по выборке: {sub['turnover_days'].median():.0f} дн"
               if len(sub) else "—")
        return med, sub[keep].to_dict("records")

    slow_med, slow_rows = _sub(inv.sort_values("turnover_days", ascending=False), slow_n)
    fast_med, fast_rows = _sub(inv.sort_values("turnover_days"), fast_n)
    return fig, slow_med, slow_rows, cols, fast_med, fast_rows, cols


# ---------------------------------------------------------------- Пополнение
@callback(Output("iv-repl-caption", "children"),
          Output("iv-repl-crit", "children"), Output("iv-repl-order", "children"),
          Output("iv-repl-ok", "children"), Output("iv-repl-dead", "children"),
          Output("iv-repl-empty", "children"), Output("iv-repl-grid", "rowData"),
          Output("iv-repl-grid", "columnDefs"),
          *_FILTERS, Input("iv-repl-action", "value"))
def _replenishment(only_profile, chambers_sel, _r, only_action):
    f = _filtered(only_profile, chambers_sel)
    lead, svc, dead, z = _repl_params()
    rep = compute_replenishment(f, lead, z, dead)
    cap = (f"Срок поставки {lead} дн., уровень сервиса {svc}% (z={z:.2f}). "
           "Точка заказа = μ·L + страховой запас; страховой запас = z·σ·√L. "
           f"SKU без отгрузок дольше {dead} дн. — «Неактивен». Параметры — в Настройках.")
    crit = int((rep["repl_status"] == "Критично").sum())
    order = int((rep["repl_status"] == "Пора заказывать").sum())
    ok = int((rep["repl_status"] == "OK").sum())
    deadn = int((rep["repl_status"] == "Неактивен").sum())

    order_map = {"Критично": 0, "Пора заказывать": 1, "OK": 2}
    if only_action:
        show = rep[rep["repl_status"].isin(["Критично", "Пора заказывать"])]
    else:
        show = rep[rep["repl_status"].isin(["Критично", "Пора заказывать", "OK"])]
    show = show.assign(_o=show["repl_status"].map(order_map)).sort_values(
        ["_o", "coverage_days"])
    if show.empty:
        empty = dbc.Alert("Нет позиций, требующих заказа под текущие фильтры. 👌",
                          color="success")
        return cap, crit, order, ok, deadn, empty, [], []

    d = show.copy()
    d["repl_status"] = d["repl_status"].map(lambda s: f"{REPL_EMOJI.get(s, '')} {s}".strip())
    for c in ("current_stock", "safety_stock", "reorder_point", "order_qty"):
        d[c] = d[c].round(0)
    d["out_mean"] = d["out_mean"].round(2)
    d["coverage_days"] = d["coverage_days"].round(1)
    cols = [
        {"field": "repl_status", "headerName": "Статус"},
        {"field": "code", "headerName": "Код 1С", "maxWidth": 110},
        {"field": "name", "headerName": "Наименование", "flex": 2},
        {"field": "chamber", "headerName": "Камера"},
        {"field": "current_stock", "headerName": "Остаток", "valueFormatter": _MONEY},
        {"field": "out_mean", "headerName": "Спрос/сут"},
        {"field": "coverage_days", "headerName": "Дни покрытия"},
        {"field": "safety_stock", "headerName": "Страх. запас", "valueFormatter": _MONEY},
        {"field": "reorder_point", "headerName": "Точка заказа", "valueFormatter": _MONEY},
        {"field": "order_qty", "headerName": "Заказать (ед.)", "valueFormatter": _MONEY},
    ]
    keep = ["repl_status", "code", "name", "chamber", "current_stock", "out_mean",
            "coverage_days", "safety_stock", "reorder_point", "order_qty"]
    return cap, crit, order, ok, deadn, None, d[keep].to_dict("records"), cols


# ---------------------------------------------------------------- Сезонный риск
@callback(Output("iv-seas-caption", "children"), Output("iv-seas-profile", "figure"),
          Output("iv-seas-need", "children"), Output("iv-seas-new", "children"),
          Output("iv-seas-days", "children"), Output("iv-seas-empty", "children"),
          Output("iv-seas-grid", "rowData"), Output("iv-seas-grid", "columnDefs"),
          *_FILTERS, Input("iv-seas-only-new", "value"))
def _seasonal(only_profile, chambers_sel, _r, only_new):
    f = _filtered(only_profile, chambers_sel)
    lead, _svc, dead, z = _repl_params()
    rep = compute_replenishment(f, lead, z, dead)
    fc, info = forecast_seasonal_risk(rep, lead)
    if info is None:
        return ("Недостаточно данных для сезонного прогноза.", go.Figure(),
                "—", "—", "—", None, [], [])

    peak_m, peak_y = info["peak_month"], int(info["peak_label"][:4])
    d2p = info["days_to_peak"]
    cap = (f"Ближайший сезонный пик — {_MONTHS_RU[peak_m]} {peak_y} "
           f"(спрос ×{info['peak_factor']:.2f}), через {d2p} дн. Пиковая точка заказа "
           f"= μ·×{info['peak_factor']:.2f}·{lead} + страховой запас. Заказывать под "
           f"пик — примерно через {max(0, d2p - lead)} дн.")
    seas = info["seas"]
    prof = pd.DataFrame({
        "Месяц": [_MONTHS_RU[m] for m in range(1, 13)],
        "Коэффициент": [round(seas.get(m, 1.0), 2) for m in range(1, 13)],
        "is_peak": [m == peak_m for m in range(1, 13)]})
    figp = px.bar(prof, x="Месяц", y="Коэффициент", color="is_peak",
                  color_discrete_map={True: BRAND["accent"], False: BRAND["secondary"]},
                  category_orders={"Месяц": [_MONTHS_RU[m] for m in range(1, 13)]},
                  title="Сезонный профиль спроса (1.0 = средний месяц)")
    figp.add_hline(y=1.0, line_dash="dot", line_color="#888")
    figp.update_layout(height=300, margin=dict(t=50), showlegend=False)

    live = fc[~fc["repl_status"].isin(["Неактивен", "—"])]
    need = live[live["preorder_qty"] > 0]
    new_peak = need[need["repl_status"] == "OK"]
    show = (new_peak if only_new else need).sort_values("preorder_qty", ascending=False)
    if show.empty:
        empty = dbc.Alert("Нет позиций с сезонным риском под текущие фильтры. 👌",
                          color="success")
        return cap, figp, len(need), len(new_peak), d2p, empty, [], []

    d = show.copy()
    for c in ("current_stock", "reorder_point", "peak_reorder_point", "preorder_qty"):
        d[c] = d[c].round(0)
    d["out_mean"] = d["out_mean"].round(2)
    d["peak_daily"] = d["peak_daily"].round(2)
    d["coverage_at_peak"] = d["coverage_at_peak"].round(1)
    cols = [
        {"field": "code", "headerName": "Код 1С", "maxWidth": 110},
        {"field": "name", "headerName": "Наименование", "flex": 2},
        {"field": "chamber", "headerName": "Камера"},
        {"field": "current_stock", "headerName": "Остаток", "valueFormatter": _MONEY},
        {"field": "out_mean", "headerName": "Спрос/сут"},
        {"field": "peak_daily", "headerName": "Спрос/сут в пик"},
        {"field": "coverage_at_peak", "headerName": "Покрытие в пик, дн"},
        {"field": "reorder_point", "headerName": "Точка заказа", "valueFormatter": _MONEY},
        {"field": "peak_reorder_point", "headerName": "Точка заказа (пик)",
         "valueFormatter": _MONEY},
        {"field": "preorder_qty", "headerName": "Предзаказ к пику", "valueFormatter": _MONEY},
    ]
    keep = ["code", "name", "chamber", "current_stock", "out_mean", "peak_daily",
            "coverage_at_peak", "reorder_point", "peak_reorder_point", "preorder_qty"]
    return cap, figp, len(need), len(new_peak), d2p, None, d[keep].to_dict("records"), cols


# ---------------------------------------------------------------- Переполнение камер
@callback(Output("iv-overflow-caption", "children"),
          Output("iv-overflow-graph", "figure"), Output("iv-overflow-table", "children"),
          Output("iv-overflow-warn", "children"),
          Input("iv-overflow-window", "value"), Input("iv-refresh", "data"))
def _overflow(window, _r):
    occ = data.occ_daily()
    cham = data.chambers()
    if occ.empty:
        return "", go.Figure(), dbc.Alert("Нет дневных остатков.", color="info"), None

    window = int(window or 60)
    cap = (f"Занятость камер по дням. Тренд — линейная аппроксимация по последним "
           f"{window} дн., экстраполяция до ёмкости даёт «дней до переполнения». "
           "Наклон ≤ 0 — переполнение не грозит.")
    capm = dict(zip(cham["chamber"], cham["capacity"]))
    rows, fig = [], go.Figure()
    for ch in sorted(occ["chamber"].unique()):
        g = occ[occ["chamber"] == ch].sort_values("day")
        win = g.tail(window)
        y = win["slots"].to_numpy(dtype=float)
        cur = float(y[-1])
        c = float(capm.get(ch, 0) or 0)
        slope = float(np.polyfit(np.arange(len(y)), y, 1)[0]) if len(y) >= 2 else 0.0
        if c and cur >= c:
            dtf, eta = 0.0, win["day"].iloc[-1]
        elif slope > 1e-6 and c:
            dtf = (c - cur) / slope
            eta = win["day"].iloc[-1] + pd.Timedelta(days=round(dtf))
        else:
            dtf, eta = None, None
        rows.append({
            "Камера": ch, "Занято": round(cur), "Ёмкость": int(c),
            "Загрузка, %": round(100 * cur / c, 1) if c else None,
            "Наклон, мест/дн": round(slope, 2),
            "Дней до переполнения": round(dtf) if dtf is not None else None,
            "Прогноз даты": eta.strftime("%Y-%m-%d") if eta is not None else "—"})
        color = chamber_color(ch)
        fig.add_scatter(x=g["day"], y=g["slots"], name=ch, mode="lines",
                        line=dict(color=color))
        if c:
            fig.add_hline(y=c, line_dash="dash", line_color=color, opacity=0.5)
    fig.update_layout(height=380, margin=dict(t=30), legend_orientation="h",
                      yaxis_title="Паллетоместа", xaxis_title="")

    summary = pd.DataFrame(rows)
    table = dbc.Table.from_dataframe(summary, striped=True, hover=True, size="sm")
    warn_rows = summary[summary["Дней до переполнения"].notna()
                        & (summary["Дней до переполнения"] <= 90)]
    warns = [dbc.Alert(f"⚠️ {r['Камера']}: при текущем тренде переполнение через "
                       f"~{int(r['Дней до переполнения'])} дн. ({r['Прогноз даты']}).",
                       color="warning", className="py-2")
             for _, r in warn_rows.iterrows()]
    return cap, fig, table, warns or None
