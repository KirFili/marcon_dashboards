"""Страница «Справочник SKU» на Dash — редактируемый ag-grid.

Порт `pages/3_Справочник_SKU.py`: правка единицы хранения и упаковочных полей.
Ручные правки фиксируются в `Sku.overrides` (приоритет над 1С, импорт их не
перетирает). Флаги: 🔒 — есть фиксация, 🆕 — черновик из ведомости, «пробел» —
нельзя посчитать паллеты. Чекбокс «Сбросить к 1С» снимает все фиксации строки.
"""

from __future__ import annotations

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update
from sqlalchemy import select

from core.db import SessionLocal
from core.inventory import has_pallet_basis
from core.models import Chamber, Sku
from core.settings import get_setting
from core.sku_fields import OVERRIDABLE, build_ref, effective

UNIT_OPTIONS = ["", "шт", "Коробка", "коробка", "г", "кг", "л", "упак"]


def _scope() -> set[str]:
    return set((get_setting("scope_groups") or "").split(","))


def _records() -> list[dict]:
    with SessionLocal() as session:
        chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
        skus = session.scalars(select(Sku).order_by(Sku.group_kind, Sku.name)).all()
        scope = _scope()
        recs = []
        for s in skus:
            ref = build_ref(s)
            recs.append({
                "id": s.id, "code": s.code, "name": s.name,
                "group_kind": s.group_kind or "", "chamber": chambers.get(s.chamber_id, ""),
                "unit": effective(s, "unit") or "",
                "units_per_box": effective(s, "units_per_box"),
                "boxes_per_pallet": effective(s, "boxes_per_pallet"),
                "boxes_per_layer": effective(s, "boxes_per_layer"),
                "layers_per_pallet": effective(s, "layers_per_pallet"),
                "units_per_pallet": effective(s, "units_per_pallet"),
                "gap": not has_pallet_basis(ref),
                "locked": bool(s.overrides),
                "draft": bool(s.is_draft),
                "profile": (s.group_kind or "")[:2] in scope,
                "reset": False,
            })
    return recs


def _filter(recs, search, only_profile, only_gaps, only_drafts):
    out = recs
    if only_profile:
        # черновики показываем всегда: они без группы (не профильные), но требуют
        # заполнения — иначе предупреждение «N новых» висит, а в списке их не найти
        out = [r for r in out if r["profile"] or r["draft"]]
    if only_gaps:
        out = [r for r in out if r["gap"]]
    if only_drafts:
        out = [r for r in out if r["draft"]]
    if search and search.strip():
        s = search.strip().lower()
        out = [r for r in out if s in r["code"].lower() or s in r["name"].lower()]
    return out


_COLS = [
    {"field": "code", "headerName": "Код 1С", "editable": False, "pinned": "left",
     "maxWidth": 120},
    {"field": "name", "headerName": "Наименование", "editable": False, "pinned": "left",
     "flex": 2, "minWidth": 220},
    {"field": "group_kind", "headerName": "Групировка", "editable": False},
    {"field": "chamber", "headerName": "Камера", "editable": False},
    {"field": "unit", "headerName": "Ед. хранения", "editable": True,
     "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": UNIT_OPTIONS}},
    {"field": "draft", "headerName": "🆕", "editable": False, "maxWidth": 70,
     "cellRenderer": "agCheckboxCellRenderer"},
    {"field": "gap", "headerName": "Пробел", "editable": False, "maxWidth": 90,
     "cellRenderer": "agCheckboxCellRenderer"},
    {"field": "locked", "headerName": "🔒", "editable": False, "maxWidth": 70,
     "cellRenderer": "agCheckboxCellRenderer"},
    {"field": "units_per_box", "headerName": "Штук в коробке", "editable": True,
     "type": "numericColumn"},
    {"field": "boxes_per_pallet", "headerName": "Коробок на паллете", "editable": True,
     "type": "numericColumn"},
    {"field": "boxes_per_layer", "headerName": "Коробов в слое", "editable": True,
     "type": "numericColumn"},
    {"field": "layers_per_pallet", "headerName": "Слоёв на паллете", "editable": True,
     "type": "numericColumn"},
    {"field": "units_per_pallet", "headerName": "Штук на паллете", "editable": True,
     "type": "numericColumn"},
    {"field": "reset", "headerName": "Сбросить к 1С", "editable": True, "maxWidth": 130,
     "cellRenderer": "agCheckboxCellRenderer"},
]


def layout():
    controls = dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([dbc.Label("Поиск (код или наименование)"),
                 dbc.Input(id="sk-search", type="text", debounce=True)], md=5),
        dbc.Col(dbc.Switch(id="sk-only-profile", label="Только профильные",
                           value=True), md=2),
        dbc.Col(dbc.Switch(id="sk-only-gaps", label="Только с пробелами",
                           value=False), md=2),
        dbc.Col(dbc.Switch(id="sk-only-drafts", label="Только черновики 🆕",
                           value=False), md=3),
    ], className="g-2")), className="mb-3")

    def kpi(title, _id):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(title, className="text-muted small"),
            html.H4(id=_id, className="mb-0")])), md=True)

    kpis = dbc.Row([kpi("Показано SKU", "sk-kpi-shown"),
                    kpi("С пробелами (в выборке)", "sk-kpi-gaps"),
                    kpi("Зафиксировано 🔒", "sk-kpi-locked"),
                    kpi("Черновики 🆕", "sk-kpi-drafts")], className="mb-3 g-2")

    grid = dag.AgGrid(
        id="sk-grid", columnDefs=_COLS, rowData=[],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 20,
                         "stopEditingWhenCellsLoseFocus": True},
        style={"height": 560})

    return html.Div([
        dcc.Store(id="sk-saved", data=0),
        html.H2("Справочник SKU"),
        html.P("Дозаполни/исправь упаковку и единицу хранения. Ручные правки "
               "фиксируются (🔒) и имеют приоритет над 1С — импорт их не "
               "перезаписывает. «Сбросить к 1С» снимает фиксации строки.",
               className="text-muted"),
        controls, kpis,
        dbc.Button("Сохранить", id="sk-save", color="primary", className="mb-2"),
        html.Span(" Смени фильтры только после сохранения — иначе правки в "
                  "выборке сбросятся.", className="text-muted small"),
        html.Div(id="sk-save-result"),
        grid,
    ])


@callback(Output("sk-grid", "rowData"),
          Output("sk-kpi-shown", "children"), Output("sk-kpi-gaps", "children"),
          Output("sk-kpi-locked", "children"), Output("sk-kpi-drafts", "children"),
          Input("sk-search", "value"), Input("sk-only-profile", "value"),
          Input("sk-only-gaps", "value"), Input("sk-only-drafts", "value"),
          Input("sk-saved", "data"))
def _populate(search, only_profile, only_gaps, only_drafts, _saved):
    recs = _records()
    view = _filter(recs, search, only_profile, only_gaps, only_drafts)
    shown = len(view)
    gaps = sum(1 for r in view if r["gap"])
    locked = sum(1 for r in recs if r["locked"])
    drafts = sum(1 for r in recs if r["draft"])
    return view, shown, gaps, locked, drafts


def _norm(field, val):
    if field == "unit":
        return None if (val is None or str(val).strip() == "") else str(val).strip()
    if val is None or val == "" or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


@callback(Output("sk-save-result", "children"), Output("sk-saved", "data"),
          Input("sk-save", "n_clicks"), State("sk-grid", "rowData"),
          State("sk-saved", "data"), prevent_initial_call=True)
def _save(n, rows, saved):
    if not rows:
        return no_update, no_update
    locked_cnt = reset_cnt = 0
    with SessionLocal() as session:
        for row in rows:
            sku = session.get(Sku, int(row["id"]))
            if sku is None:
                continue
            if row.get("reset"):
                if sku.overrides:
                    reset_cnt += 1
                sku.overrides = {}
                continue
            ov = {}
            for f in OVERRIDABLE:
                ev = _norm(f, row.get(f))
                base = getattr(sku, f)
                base = base.lower() if (f == "unit" and isinstance(base, str)) else base
                cmp = ev.lower() if (f == "unit" and isinstance(ev, str)) else ev
                if cmp != base:
                    ov[f] = ev
            sku.overrides = ov
            if ov:
                locked_cnt += 1
        session.commit()
    msg = dbc.Alert(f"Сохранено. Зафиксировано строк: {locked_cnt}, сброшено: "
                    f"{reset_cnt}.", color="success", dismissable=True)
    return msg, (saved or 0) + 1
