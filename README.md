# marcon_dashboards

Веб-платформа аналитических дашбордов группы компаний Маркон. Каждый дашборд — отдельная вкладка единого приложения.

## Состав

- **Маржинальный доход** — для руководства и акционеров. Динамика валовой прибыли в разрезах.
- **Управление товарооборотом** — для склада и аналитиков. Паллетоместа, оборачиваемость, индекс мёртвости SKU. ТЗ: [`docs/inventory_spec.md`](docs/inventory_spec.md).

## Стек

- Python 3.13, Streamlit, Plotly
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
uv run streamlit run Home.py
```

Дашборд: <http://dashboard.localhost:8501> (на macOS `*.localhost` резолвится в `127.0.0.1` автоматически).

Пароль из `.env` → `DASHBOARD_PASSWORD`.

## Структура

```
Home.py              точка входа Streamlit
pages/               остальные вкладки (Streamlit multipage)
core/                бизнес-логика, переиспользуется между вкладками
db/migrations/       Alembic
docs/                ТЗ дашбордов
```
