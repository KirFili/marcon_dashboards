import streamlit as st

from core.auth import require_password

st.set_page_config(
    page_title="Marcon Dashboards",
    page_icon="📊",
    layout="wide",
)

require_password()

st.title("Marcon Dashboards")
st.markdown(
    """
Веб-платформа аналитических дашбордов группы компаний Маркон.

**Доступные вкладки** (слева в навигации):

- **Маржинальный доход** — динамика валовой прибыли для руководства и акционеров.
- **Управление товарооборотом** — паллетоместа, оборачиваемость, индекс мёртвости SKU.
- **Настройки** — камеры хранения, порог хвоста паллеты, загрузка отчётов 1С.
"""
)
