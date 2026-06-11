"""Dash-приложение Маркона (миграция со Streamlit).

Запуск (dev):   uv run python -m dash_app.app
Запуск (prod):  gunicorn dash_app.app:server   (server = Flask-приложение)

Конфиг через env: DATABASE_URL (см. core.db), DASHBOARD_PASSWORD, SECRET_KEY.
"""

from __future__ import annotations

import os
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, callback, dcc, html, no_update
from dotenv import load_dotenv
from flask import session

from core.settings import bootstrap_defaults
from dash_app import auth
from dash_app.components import shell
from dash_app.views import (  # noqa: F401 — регистрирует callbacks
    inventory,
    settings_page,
    skus,
    turnover,
    upload,
)

load_dotenv()

_ASSETS = str(Path(__file__).resolve().parent.parent / "assets")

app = Dash(__name__, assets_folder=_ASSETS,
           external_stylesheets=[dbc.themes.FLATLY],
           suppress_callback_exceptions=True, title="Маркон · Аналитика")
server = app.server
server.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

bootstrap_defaults()

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="login-trigger"),
    html.Div(id="root"),
])


@callback(Output("root", "children"),
          Input("url", "pathname"), Input("login-trigger", "data"))
def _render(pathname, _trigger):
    if not auth.is_authed():
        return auth.login_layout()
    return shell(pathname)


@callback(Output("login-trigger", "data"), Output("login-err", "children"),
          Input("login-btn", "n_clicks"), Input("login-pwd", "n_submit"),
          State("login-pwd", "value"), prevent_initial_call=True)
def _login(n_clicks, n_submit, pwd):
    if not n_clicks and not n_submit:  # холостое срабатывание при появлении формы
        return no_update, no_update
    if pwd == auth.PASSWORD:
        session["authed"] = True
        return (n_clicks or 0) + (n_submit or 0), ""
    return no_update, dbc.Alert("Неверный пароль", color="danger", className="mt-2")


@callback(Output("login-trigger", "data", allow_duplicate=True),
          Input("logout-btn", "n_clicks"), prevent_initial_call=True)
def _logout(n):
    session.pop("authed", None)
    return n


@callback(Output("drafts-modal", "is_open"), Input("drafts-modal-close", "n_clicks"),
          prevent_initial_call=True)
def _close_drafts(n):
    return False


if __name__ == "__main__":
    app.run(debug=True, port=8050)
