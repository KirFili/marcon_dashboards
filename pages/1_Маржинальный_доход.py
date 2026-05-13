import streamlit as st

from core.auth import require_password

st.set_page_config(page_title="Маржинальный доход", page_icon="📊", layout="wide")
require_password()

st.title("Маржинальный доход")
st.info("Вкладка в разработке. ТЗ ещё не зафиксировано.")
