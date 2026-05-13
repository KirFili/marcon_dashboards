import streamlit as st

from core.auth import require_password

st.set_page_config(page_title="Настройки", page_icon="⚙️", layout="wide")
require_password()

st.title("Настройки")
st.info("В разработке: камеры хранения, порог хвоста паллеты, окно мёртвости, загрузка отчётов 1С.")
