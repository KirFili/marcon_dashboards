"""Страница «Настройки» на Dash.

Порт `pages/99_Настройки.py`: параметры расчётов, пороги ABC/XYZ, параметры
пополнения и редактор камер хранения (ag-grid с добавлением/удалением строк).
"""

from __future__ import annotations

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update
from sqlalchemy import select

from core.db import SessionLocal
from core.models import Chamber
from core.settings import get_setting, set_setting
from dash_app import data


def _num(_id, label, value, **kw):
    return dbc.Col([dbc.Label(label),
                    dbc.Input(id=_id, type="number", value=value, **kw)], md=3)


def _chamber_rows():
    with SessionLocal() as s:
        return [{"id": c.id, "name": c.name, "temperature_c": c.temperature_c,
                 "capacity_pallets": c.capacity_pallets, "sort_order": c.sort_order,
                 "is_active": c.is_active}
                for c in s.scalars(select(Chamber).order_by(Chamber.sort_order))]


_CH_COLS = [
    {"field": "id", "headerName": "ID", "editable": False, "maxWidth": 80},
    {"field": "name", "headerName": "Название", "editable": True, "flex": 2},
    {"field": "temperature_c", "headerName": "Температура, °C", "editable": True,
     "type": "numericColumn"},
    {"field": "capacity_pallets", "headerName": "Ёмкость, паллетомест",
     "editable": True, "type": "numericColumn"},
    {"field": "sort_order", "headerName": "Порядок", "editable": True,
     "type": "numericColumn"},
    {"field": "is_active", "headerName": "Активна", "editable": True,
     "cellRenderer": "agCheckboxCellRenderer"},
]


def layout():
    g = lambda k, d: int(get_setting(k) or d)
    baseline = get_setting("seasonal_baseline") or "year_over_year"

    params = dbc.Card(dbc.CardBody([
        html.H5("Параметры расчётов"),
        dbc.Row([
            _num("se-tail", "Порог хвоста паллеты, %", g("pallet_tail_threshold_pct", 10),
                 min=0, max=100, step=1),
            _num("se-dead", "Окно индекса мёртвости, дней", g("dead_window_days", 90),
                 min=1, max=365, step=1),
            dbc.Col([dbc.Label("Сезонный baseline"),
                     dcc.Dropdown(id="se-baseline", value=baseline, clearable=False,
                                  options=[{"label": "год-к-году", "value": "year_over_year"},
                                           {"label": "медианный профиль", "value": "median_profile"}])],
                    md=3),
        ], className="g-2"),
        dbc.Button("Сохранить параметры", id="se-save-params", color="primary",
                   className="mt-2"),
        html.Div(id="se-params-result"),
    ]), className="mb-3")

    abc = dbc.Card(dbc.CardBody([
        html.H5("Пороги ABC / XYZ"),
        dbc.Row([
            _num("se-abc-a", "ABC: класс A до, %", g("abc_a_pct", 80), min=1, max=99, step=1),
            _num("se-abc-b", "ABC: класс B до, %", g("abc_b_pct", 95), min=1, max=100, step=1),
            _num("se-xyz-x", "XYZ: класс X до, % (CV)", g("xyz_x_pct", 10), min=1, max=200, step=1),
            _num("se-xyz-y", "XYZ: класс Y до, % (CV)", g("xyz_y_pct", 25), min=1, max=300, step=1),
        ], className="g-2"),
        dbc.Button("Сохранить пороги ABC/XYZ", id="se-save-abc", color="primary",
                   className="mt-2"),
        html.Div(id="se-abc-result"),
    ]), className="mb-3")

    repl = dbc.Card(dbc.CardBody([
        html.H5("Пополнение запасов"),
        dbc.Row([
            _num("se-lead", "Срок поставки (заказ→приход), дней", g("lead_time_days", 14),
                 min=1, max=180, step=1),
            _num("se-svc", "Целевой уровень сервиса, %", g("service_level_pct", 95),
                 min=50, max=99, step=1),
        ], className="g-2"),
        dbc.Button("Сохранить параметры пополнения", id="se-save-repl", color="primary",
                   className="mt-2"),
        html.Div(id="se-repl-result"),
    ]), className="mb-3")

    chambers = dbc.Card(dbc.CardBody([
        html.H5("Камеры хранения"),
        html.P("Редактируй ёмкости/температуру, добавляй и удаляй камеры.",
               className="text-muted small"),
        dag.AgGrid(id="se-ch-grid", columnDefs=_CH_COLS, rowData=_chamber_rows(),
                   defaultColDef={"sortable": True, "resizable": True},
                   dashGridOptions={"rowSelection": "multiple",
                                    "stopEditingWhenCellsLoseFocus": True},
                   style={"height": 280}),
        html.Div([
            dbc.Button("➕ Добавить камеру", id="se-ch-add", color="secondary",
                       outline=True, size="sm", className="me-2 mt-2"),
            dbc.Button("🗑 Удалить выбранные", id="se-ch-del", color="secondary",
                       outline=True, size="sm", className="me-2 mt-2"),
            dbc.Button("Сохранить камеры", id="se-ch-save", color="primary",
                       size="sm", className="mt-2"),
        ]),
        html.Div(id="se-ch-result"),
    ]), className="mb-3")

    return html.Div([html.H2("Настройки"), params, abc, repl, chambers])


def _ok(msg):
    return dbc.Alert(msg, color="success", dismissable=True, className="mt-2")


@callback(Output("se-params-result", "children"), Input("se-save-params", "n_clicks"),
          State("se-tail", "value"), State("se-dead", "value"),
          State("se-baseline", "value"), prevent_initial_call=True)
def _save_params(n, tail, dead, baseline):
    set_setting("pallet_tail_threshold_pct", int(tail), "int")
    set_setting("dead_window_days", int(dead), "int")
    set_setting("seasonal_baseline", baseline, "str")
    data.clear()
    return _ok("Параметры сохранены.")


@callback(Output("se-abc-result", "children"), Input("se-save-abc", "n_clicks"),
          State("se-abc-a", "value"), State("se-abc-b", "value"),
          State("se-xyz-x", "value"), State("se-xyz-y", "value"),
          prevent_initial_call=True)
def _save_abc(n, a, b, x, y):
    if b <= a:
        return dbc.Alert("Порог B должен быть больше A.", color="danger", className="mt-2")
    if y <= x:
        return dbc.Alert("Порог Y должен быть больше X.", color="danger", className="mt-2")
    for k, v in [("abc_a_pct", a), ("abc_b_pct", b), ("xyz_x_pct", x), ("xyz_y_pct", y)]:
        set_setting(k, int(v), "int")
    data.clear()
    return _ok("Пороги сохранены.")


@callback(Output("se-repl-result", "children"), Input("se-save-repl", "n_clicks"),
          State("se-lead", "value"), State("se-svc", "value"),
          prevent_initial_call=True)
def _save_repl(n, lead, svc):
    set_setting("lead_time_days", int(lead), "int")
    set_setting("service_level_pct", int(svc), "int")
    data.clear()
    return _ok("Параметры пополнения сохранены.")


@callback(Output("se-ch-grid", "rowData"), Input("se-ch-add", "n_clicks"),
          State("se-ch-grid", "rowData"), prevent_initial_call=True)
def _ch_add(n, rows):
    rows = list(rows or [])
    rows.append({"id": None, "name": "", "temperature_c": 0,
                 "capacity_pallets": 0, "sort_order": len(rows) + 1, "is_active": True})
    return rows


@callback(Output("se-ch-grid", "rowData", allow_duplicate=True),
          Input("se-ch-del", "n_clicks"), State("se-ch-grid", "rowData"),
          State("se-ch-grid", "selectedRows"), prevent_initial_call=True)
def _ch_del(n, rows, selected):
    if not selected:
        return no_update
    return [r for r in (rows or []) if r not in selected]


@callback(Output("se-ch-result", "children"),
          Output("se-ch-grid", "rowData", allow_duplicate=True),
          Input("se-ch-save", "n_clicks"), State("se-ch-grid", "rowData"),
          prevent_initial_call=True)
def _ch_save(n, rows):
    rows = rows or []
    keep_ids = {int(r["id"]) for r in rows if r.get("id") not in (None, "")}
    with SessionLocal() as s:
        db_ids = {c.id for c in s.scalars(select(Chamber))}
        for cid in db_ids - keep_ids:
            obj = s.get(Chamber, cid)
            if obj:
                s.delete(obj)
        for r in rows:
            name = str(r.get("name") or "").strip()
            if not name:
                continue
            vals = dict(name=name, temperature_c=float(r.get("temperature_c") or 0),
                        capacity_pallets=int(r.get("capacity_pallets") or 0),
                        sort_order=int(r.get("sort_order") or 0),
                        is_active=bool(r.get("is_active", True)))
            if r.get("id") in (None, ""):
                s.add(Chamber(**vals))
            else:
                obj = s.get(Chamber, int(r["id"]))
                if obj:
                    for k, v in vals.items():
                        setattr(obj, k, v)
        s.commit()
    data.clear()
    return _ok("Камеры сохранены."), _chamber_rows()
