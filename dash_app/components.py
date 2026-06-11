"""Оболочка приложения: шапка с логотипом, боковая навигация, контент.

Пока перенесена только страница «Товарооборот»; остальные разделы — заглушки
(переносятся в следующих вехах миграции).
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html
from sqlalchemy import func, select

from core.db import SessionLocal
from core.models import Sku
from dash_app.views import inventory, settings_page, skus, turnover, upload

NAV = [
    {"path": "/", "label": "Товарооборот", "icon": "📦", "ready": True},
    {"path": "/inventory", "label": "Управление запасами", "icon": "🧮", "ready": True},
    {"path": "/skus", "label": "Справочник SKU", "icon": "📇", "ready": True},
    {"path": "/upload", "label": "Загрузка данных", "icon": "📥", "ready": True},
    {"path": "/settings", "label": "Настройки", "icon": "⚙️", "ready": True},
]


def draft_count() -> int:
    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(Sku).where(Sku.is_draft)) or 0


def _sidebar(pathname):
    links = []
    for n in NAV:
        label = f'{n["icon"]} {n["label"]}'
        if not n.get("ready"):
            links.append(html.Span(label, className="nav-link disabled text-muted"))
        else:
            active = pathname == n["path"] or (pathname in (None, "") and n["path"] == "/")
            links.append(dcc.Link(label, href=n["path"],
                                  className="nav-link active" if active else "nav-link"))
    return dbc.Nav(links, vertical=True, pills=True)


def page_for(pathname):
    if pathname in ("/", None, ""):
        return turnover.layout()
    if pathname == "/inventory":
        return inventory.layout()
    if pathname == "/skus":
        return skus.layout()
    if pathname == "/upload":
        return upload.layout()
    if pathname == "/settings":
        return settings_page.layout()
    return dbc.Alert("Раздел не найден.", color="info")


def shell(pathname):
    """Каркас после входа: шапка + навигация + контент (наполнен сразу под текущий
    путь). Переходы обновляют только sidebar/page-content (callback по url.pathname);
    гейт авторизации при переходах НЕ пере-рендерится → разлогинить навигацией нельзя.
    """
    header = dbc.Navbar(dbc.Container([
        dbc.Row([
            dbc.Col(html.Img(src="/assets/stardogs_logo.png", height="36px")),
            dbc.Col(dbc.NavbarBrand("Маркон · Аналитика", className="ms-2")),
        ], align="center", className="g-2"),
        dbc.Button("Выйти", id="logout-btn", color="light", size="sm", n_clicks=0),
    ], fluid=True), color="primary", dark=True, className="mb-3")

    body = dbc.Container(dbc.Row([
        dbc.Col(html.Div(_sidebar(pathname), id="sidebar"), md=2),
        dbc.Col(html.Div(page_for(pathname), id="page-content"), md=10),
    ]), fluid=True)

    return html.Div([header, body])
