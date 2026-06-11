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

from core.settings import bootstrap_defaults
from dash_app import auth
from dash_app.components import _sidebar, draft_count, page_for, shell
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

# Авторизация — клиентский флаг в sessionStorage (переживает переходы и reload
# вкладки), пароль проверяется на сервере в _login. drafts-warned — чтобы окно
# о черновиках показалось один раз за сессию.
app.layout = html.Div([
    dcc.Location(id="url"),
    # auth — sessionStorage (переживает reload вкладки); drafts-warned — memory
    # (показать окно раз за загрузку, на reload снова — это ок).
    dcc.Store(id="auth-store", storage_type="session", data=False),
    dcc.Store(id="drafts-warned-store", data=False),
    html.Div(id="drafts-modal-container"),  # модалку целиком кладёт callback
    html.Div(id="root"),
])


# Гейт авторизации — реагирует ТОЛЬКО на смену auth-store (вход/выход).
# Контент сразу наполняется под текущий путь (State), без гонки монтирования.
# Переходы между страницами этот callback НЕ трогают → навигацией не разлогинить.
@callback(Output("root", "children"), Input("auth-store", "data"),
          State("url", "pathname"))
def _render_auth(authed, pathname):
    return shell(pathname) if authed else auth.login_layout()


# Переход — обновляет меню и контент по url (только при реальной смене пути).
@callback(Output("sidebar", "children"), Output("page-content", "children"),
          Input("url", "pathname"), prevent_initial_call=True)
def _nav(pathname):
    return _sidebar(pathname), page_for(pathname)


@callback(Output("auth-store", "data"), Output("login-err", "children"),
          Input("login-btn", "n_clicks"), Input("login-pwd", "n_submit"),
          State("login-pwd", "value"), prevent_initial_call=True)
def _login(n_clicks, n_submit, pwd):
    if not n_clicks and not n_submit:  # холостое срабатывание при появлении формы
        return no_update, no_update
    if pwd == auth.PASSWORD:
        return True, ""
    return no_update, dbc.Alert("Неверный пароль", color="danger", className="mt-2")


@callback(Output("auth-store", "data", allow_duplicate=True),
          Input("logout-btn", "n_clicks"), prevent_initial_call=True)
def _logout(n):
    return False


@callback(Output("drafts-modal-container", "children"),
          Output("drafts-warned-store", "data"),
          Input("auth-store", "data"), State("drafts-warned-store", "data"),
          prevent_initial_call=True)
def _maybe_drafts(authed, warned):
    if not authed or warned:
        return no_update, no_update
    n = draft_count()
    if not n:
        return no_update, True
    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("⚠️ Требуется обновление справочника")),
        dbc.ModalBody(dbc.Alert(f"{n} новых позиций. Обновите справочник SKU из 1С.",
                                color="warning", className="mb-0")),
        dbc.ModalFooter(dbc.Button("Понятно", id="drafts-modal-close",
                                   color="primary")),
    ], id="drafts-modal", is_open=True)
    return modal, True


@callback(Output("drafts-modal", "is_open"),
          Input("drafts-modal-close", "n_clicks"), prevent_initial_call=True)
def _close_drafts(n):
    return False


if __name__ == "__main__":
    app.run(debug=True, port=8050)
