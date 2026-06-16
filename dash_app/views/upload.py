"""Страница «Загрузка данных» на Dash.

Порт `pages/4_Загрузка_данных.py`: мультизагрузка дневных остатков, справочника
и продаж через `dcc.Upload`, календарь покрытия дней, история загрузок,
предупреждение о новых черновиках SKU.
"""

from __future__ import annotations

import base64
import calendar
import os
import tempfile
from pathlib import Path

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html
from sqlalchemy import func, select

from core.db import SessionLocal
from core.fmt import money
from core.ingest import import_sales, import_skus, import_stock_daily
from core.models import Sale, Sku, StockDaily, Upload
from dash_app import data

MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
             "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
KIND_RU = {"sku": "справочник", "sales": "продажи", "stock": "остатки (мес)",
           "stock_daily": "остатки (день)"}


def _decode_to_temp(content: str, name: str) -> str:
    _, b64 = content.split(",", 1)
    suffix = Path(name).suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(base64.b64decode(b64))
    tmp.close()
    return tmp.name


def _process(contents, names, importer) -> list[dict]:
    if not contents:
        return []
    if isinstance(contents, str):
        contents, names = [contents], [names]
    rows = []
    for content, name in zip(contents, names):
        p = _decode_to_temp(content, name)
        try:
            if "filename" in importer.__code__.co_varnames:
                r = importer(p, filename=name)
            else:
                r = importer(p)
        except Exception as e:  # noqa: BLE001
            r = {"skipped": True, "reason": f"ошибка: {e}"}
        finally:
            os.unlink(p)
        rows.append({
            "Файл": name, "День/итог": r.get("day", "—"),
            "Создано": r.get("created", 0), "Обновлено": r.get("updated", 0),
            "Новые SKU 🆕": r.get("created_sku", 0),
            "Пропущено (нет SKU)": r.get("skipped_no_sku", 0),
            "Статус": r.get("reason", "ок"),
        })
    data.clear()
    return rows


def _result(rows) -> list:
    if not rows:
        return []
    loaded = sum(1 for r in rows if r["Статус"] == "ок")
    out = [dbc.Alert(f"Загружено: {loaded} из {len(rows)}.", color="success",
                     dismissable=True),
           dbc.Table.from_dataframe(pd.DataFrame(rows), striped=True, size="sm")]
    new_cnt = sum(r.get("Новые SKU 🆕", 0) for r in rows)
    if new_cnt:
        out.append(dbc.Alert(
            f"🆕 Заведено новых черновиков SKU: {new_cnt}. Дозаполни упаковку в "
            "разделе «Справочник SKU» (фильтр «Только черновики»).",
            color="warning"))
    return out


def _uploader(_id, text, multiple):
    return dcc.Upload(id=_id, multiple=multiple, className="mb-2",
                      children=html.Div(["⬆ ", text]),
                      style={"borderWidth": "1px", "borderStyle": "dashed",
                             "borderRadius": "8px", "padding": "18px",
                             "textAlign": "center"})


def layout():
    return html.Div([
        dcc.Store(id="up-refresh", data=0),
        html.H2("Загрузка данных"),
        html.P("Выгрузки 1С: справочник, продажи (помесячно), дневные остатки.",
               className="text-muted"),
        html.H5("📅 Дневные остатки (ведомость по товарам)"),
        html.P("Можно выбрать сразу много файлов — по одному на день. День берётся "
               "из «Период» внутри файла.", className="text-muted small"),
        _uploader("up-daily", "Перетащи или выбери дневные ведомости (.xlsx)", True),
        html.Div(id="up-daily-result"),
        dbc.Button(id="up-cov-toggle", color="link", n_clicks=0,
                   className="mt-3 p-0 text-decoration-none"),
        dbc.Collapse(html.Div(id="up-coverage"), id="up-cov-collapse",
                     is_open=False),
        html.Hr(),
        dbc.Row([
            dbc.Col([html.H5("📒 Справочник SKU"),
                     _uploader("up-ref", "Справочник (.xls/.xlsx)", False),
                     html.Div(id="up-ref-result")], md=6),
            dbc.Col([html.H5("💰 Продажи (помесячно)"),
                     _uploader("up-sales", "Отчёт продаж (.xlsx)", False),
                     html.Div(id="up-sales-result"),
                     dbc.Button(id="up-sales-cov-toggle", color="link", n_clicks=0,
                                className="mt-2 p-0 text-decoration-none"),
                     dbc.Collapse(html.Div(id="up-sales-coverage"),
                                  id="up-sales-cov-collapse", is_open=False)], md=6),
        ]),
        html.Hr(),
        html.H5("📜 История загрузок"),
        html.Div(id="up-history"),
    ])


@callback(Output("up-daily-result", "children"), Output("up-refresh", "data"),
          Input("up-daily", "contents"), Input("up-daily", "filename"),
          State("up-refresh", "data"), prevent_initial_call=True)
def _up_daily(contents, names, n):
    rows = _process(contents, names, import_stock_daily)
    return _result(rows), (n or 0) + 1


@callback(Output("up-ref-result", "children"),
          Output("up-refresh", "data", allow_duplicate=True),
          Input("up-ref", "contents"), Input("up-ref", "filename"),
          State("up-refresh", "data"), prevent_initial_call=True)
def _up_ref(contents, names, n):
    rows = _process(contents, names, import_skus)
    return _result(rows), (n or 0) + 1


@callback(Output("up-sales-result", "children"),
          Output("up-refresh", "data", allow_duplicate=True),
          Input("up-sales", "contents"), Input("up-sales", "filename"),
          State("up-refresh", "data"), prevent_initial_call=True)
def _up_sales(contents, names, n):
    rows = _process(contents, names, import_sales)
    return _result(rows), (n or 0) + 1


@callback(Output("up-coverage", "children"), Output("up-history", "children"),
          Output("up-cov-toggle", "children"),
          Output("up-sales-coverage", "children"),
          Output("up-sales-cov-toggle", "children"),
          Input("up-refresh", "data"))
def _coverage_history(_r):
    with SessionLocal() as s:
        days = [d for (d,) in s.execute(
            select(StockDaily.day).distinct().order_by(StockDaily.day))]
        sales = s.execute(
            select(Sale.period, func.count(func.distinct(Sale.sku_id)),
                   func.sum(Sale.revenue))
            .group_by(Sale.period).order_by(Sale.period)).all()
        ups = s.scalars(select(Upload).order_by(Upload.uploaded_at.desc())
                        .limit(50)).all()
        hist_rows = [{"Когда": u.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                      "Тип": KIND_RU.get(u.kind, u.kind), "Файл": u.filename,
                      "Строк": u.row_count} for u in ups]

    if not days:
        cov = dbc.Alert("Дневных остатков пока нет — загрузите ведомости выше.",
                        color="info")
        cov_lbl = "🗓️ Покрытие по дням — нет данных ▾"
    else:
        by = {}
        for d in days:
            by.setdefault((d.year, d.month), set()).add(d.day)
        rows = []
        for (y, m), present in sorted(by.items()):
            total = calendar.monthrange(y, m)[1]
            missing = sorted(set(range(1, total + 1)) - present)
            rows.append({"Месяц": f"{MONTHS_RU[m - 1]} {y}",
                         "Покрыто": f"{len(present)}/{total}",
                         "Полный": "✅" if not missing else "",
                         "Пропущены дни": ", ".join(map(str, missing)) or "—"})
        head = dbc.Row([
            dbc.Col(html.Div([html.Div("Дней с данными", className="text-muted small"),
                              html.H5(len(days))])),
            dbc.Col(html.Div([html.Div("Первый день", className="text-muted small"),
                              html.H5(str(days[0]))])),
            dbc.Col(html.Div([html.Div("Последний день", className="text-muted small"),
                              html.H5(str(days[-1]))])),
        ], className="mb-2")
        cov = html.Div([head, dbc.Table.from_dataframe(
            pd.DataFrame(rows), striped=True, size="sm")])
        cov_lbl = f"🗓️ Покрытие по дням — {len(days)} дн. ▾"

    if not sales:
        scov = dbc.Alert("Продаж пока нет — загрузите отчёт продаж.", color="info")
        scov_lbl = "📆 Покрытие продаж — нет данных ▾"
    else:
        srows = [{"Месяц": f"{MONTHS_RU[p.month - 1]} {p.year}", "SKU": cnt,
                  "Выручка": money(rev or 0)} for (p, cnt, rev) in sales]
        shead = dbc.Row([
            dbc.Col(html.Div([html.Div("Месяцев", className="text-muted small"),
                              html.H5(len(sales))])),
            dbc.Col(html.Div([html.Div("Первый месяц", className="text-muted small"),
                              html.H5(srows[0]["Месяц"])])),
            dbc.Col(html.Div([html.Div("Последний месяц", className="text-muted small"),
                              html.H5(srows[-1]["Месяц"])])),
        ], className="mb-2")
        scov = html.Div([shead, dbc.Table.from_dataframe(
            pd.DataFrame(srows), striped=True, size="sm")])
        scov_lbl = f"📆 Покрытие продаж — {len(sales)} мес. ▾"

    hist = dbc.Table.from_dataframe(pd.DataFrame(hist_rows), striped=True, size="sm") \
        if hist_rows else dbc.Alert("Загрузок пока нет.", color="info")
    return cov, hist, cov_lbl, scov, scov_lbl


@callback(Output("up-cov-collapse", "is_open"),
          Input("up-cov-toggle", "n_clicks"),
          State("up-cov-collapse", "is_open"), prevent_initial_call=True)
def _toggle_cov(_n, is_open):
    return not is_open


@callback(Output("up-sales-cov-collapse", "is_open"),
          Input("up-sales-cov-toggle", "n_clicks"),
          State("up-sales-cov-collapse", "is_open"), prevent_initial_call=True)
def _toggle_sales_cov(_n, is_open):
    return not is_open
