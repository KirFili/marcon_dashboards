"""Простой пароль-гейт через Flask-сессию (роли пока не нужны).

Источник правды — `flask.session` (подписанная кука, secret_key из env), что
переносимо на сервер. Пароль — из переменной окружения `DASHBOARD_PASSWORD`.
"""

from __future__ import annotations

import os

import dash_bootstrap_components as dbc
from dash import dcc, html
from flask import session

PASSWORD = os.getenv("DASHBOARD_PASSWORD", "marcon")
LOGO_URL = "/assets/stardogs_logo.png"


def is_authed() -> bool:
    return bool(session.get("authed"))


def login_layout():
    return dbc.Container(
        dbc.Row(
            dbc.Col(
                [
                    html.Img(src=LOGO_URL, style={"width": "240px"},
                             className="mb-3"),
                    html.H3("Аналитические дашборды Маркон", className="mb-4"),
                    html.Div(
                        [
                            dbc.Input(id="login-pwd", type="password",
                                      placeholder="Введите пароль", n_submit=0,
                                      style={"maxWidth": "220px"}),
                            dbc.Button("Войти", id="login-btn", color="primary",
                                       n_clicks=0, className="ms-2"),
                        ],
                        className="d-flex justify-content-center align-items-center",
                    ),
                    html.Div(id="login-err", className="mt-2"),
                ],
                width={"size": 6, "offset": 3},
                className="text-center mt-5",
            )
        ),
        fluid=True,
    )
