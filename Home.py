from pathlib import Path

import streamlit as st

from core.auth import require_password
from core.settings import bootstrap_defaults

st.set_page_config(
    page_title="Маркон · Аналитика",
    page_icon="🏠",
    layout="wide",
)

require_password()
bootstrap_defaults()

# Адаптивный размер KPI-метрик: ужимается на узких экранах, чтобы длинные
# значения («млрд ₽», «тыс ₽/мес») не обрезались. Применяется ко всем страницам.
st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] {
        font-size: clamp(0.85rem, 1.6vw, 1.7rem);
        line-height: 1.2;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    [data-testid="stMetricLabel"] p {
        font-size: clamp(0.72rem, 0.95vw, 0.9rem);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

_LOGO = Path(__file__).resolve().parent / "assets" / "stardogs_logo.png"


def home():
    col, _ = st.columns([1, 3])
    with col:
        if _LOGO.exists():
            st.image(str(_LOGO), width=240)
    st.title("Аналитические дашборды Маркон")
    st.markdown(
        """
Веб-платформа аналитических дашбордов группы компаний Маркон.

**Доступные разделы** (слева в навигации):

- **Управление товарооборотом** — паллетоместа, оборачиваемость, эффективность и сезонность SKU.
- **Управление запасами** — ABC/XYZ, пополнение (страховой запас, точка заказа), сезонный риск, переполнение камер.
- **Справочник SKU** — упаковка и единицы хранения, ручные фиксации.
- **Загрузка данных** — импорт отчётов 1С (остатки, продажи, справочник).
- **Настройки** — камеры, пороги расчётов, параметры пополнения.
"""
    )


# Меню: порядок и видимость. «Маржинальный доход» намеренно скрыт.
pages = [
    st.Page(home, title="Домой", icon="🏠", default=True),
    st.Page("pages/2_Управление_товарооборотом.py",
            title="Управление товарооборотом", icon="📦"),
    st.Page("pages/5_Управление_запасами.py",
            title="Управление запасами", icon="🧮"),
    st.Page("pages/3_Справочник_SKU.py", title="Справочник SKU", icon="📇"),
    st.Page("pages/4_Загрузка_данных.py", title="Загрузка данных", icon="📥"),
    st.Page("pages/99_Настройки.py", title="Настройки", icon="⚙️"),
]

st.navigation(pages).run()
