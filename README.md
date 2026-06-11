# marcon_dashboards

Веб-платформа аналитических дашбордов группы компаний Маркон. Каждый дашборд — отдельная вкладка единого приложения.

## Состав

- **Маржинальный доход** — для руководства и акционеров. Динамика валовой прибыли в разрезах.
- **Управление товарооборотом** — для склада и аналитиков. Паллетоместа, оборачиваемость, индекс мёртвости SKU. ТЗ: [`docs/inventory_spec.md`](docs/inventory_spec.md).

## Стек

- Python 3.13, Dash (на Flask), Plotly, dash-bootstrap-components, dash-ag-grid
- Postgres 16
- SQLAlchemy + Alembic
- Управление зависимостями: [uv](https://docs.astral.sh/uv/)

## Локальный запуск

```bash
# одноразово
brew install uv postgresql@16
brew services start postgresql@16
createdb marcon_dashboards

cp .env.example .env  # отредактировать при необходимости

uv sync
uv run alembic upgrade head

# dev-сервер
uv run python -m dash_app.app
# прод
uv run gunicorn dash_app.app:server
```

Дашборд: <http://localhost:8050>. Пароль из `.env` → `DASHBOARD_PASSWORD`
(подпись cookie — `SECRET_KEY` из `.env`).

## Структура

```
dash_app/app.py        точка входа Dash (server = Flask-приложение для gunicorn)
dash_app/components.py  оболочка: навигация, авторизация, окно черновиков
dash_app/views/         страницы (turnover, inventory, skus, upload, settings_page)
dash_app/data.py        кэширующие обёртки над core/
core/                   бизнес-логика, переиспользуется страницами
db/migrations/          Alembic
docs/                   ТЗ дашбордов
```
