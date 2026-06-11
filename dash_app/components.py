"""Оболочка приложения: шапка с логотипом, боковая навигация, контент.

Пока перенесена только страница «Товарооборот»; остальные разделы — заглушки
(переносятся в следующих вехах миграции).
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from dash_app.views import turnover

NAV = [
    {"path": "/", "label": "Товарооборот", "icon": "📦", "ready": True},
    {"path": "/inventory", "label": "Управление запасами", "icon": "🧮"},
    {"path": "/skus", "label": "Справочник SKU", "icon": "📇"},
    {"path": "/upload", "label": "Загрузка данных", "icon": "📥"},
    {"path": "/settings", "label": "Настройки", "icon": "⚙️"},
]


def _sidebar(pathname):
    links = [
        dbc.NavLink(f'{n["icon"]} {n["label"]}', href=n["path"],
                    active=(pathname == n["path"]), disabled=not n.get("ready"))
        for n in NAV
    ]
    return dbc.Nav(links, vertical=True, pills=True)


def _page(pathname):
    if pathname in ("/", None, ""):
        return turnover.layout()
    return dbc.Alert("Раздел переносится на Dash в следующих вехах миграции.",
                     color="info")


def shell(pathname):
    header = dbc.Navbar(dbc.Container([
        dbc.Row([
            dbc.Col(html.Img(src="/assets/stardogs_logo.png", height="36px")),
            dbc.Col(dbc.NavbarBrand("Маркон · Аналитика", className="ms-2")),
        ], align="center", className="g-2"),
        dbc.Button("Выйти", id="logout-btn", color="light", size="sm", n_clicks=0),
    ], fluid=True), color="primary", dark=True, className="mb-3")

    body = dbc.Container(dbc.Row([
        dbc.Col(_sidebar(pathname), md=2),
        dbc.Col(_page(pathname), md=10),
    ]), fluid=True)

    return html.Div([header, body])
