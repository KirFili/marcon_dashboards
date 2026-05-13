import streamlit as st

from core.auth import require_password

st.set_page_config(page_title="Управление товарооборотом", page_icon="📦", layout="wide")
require_password()

st.title("Управление товарооборотом")
st.info("Вкладка в разработке. ТЗ: `docs/inventory_spec.md`.")
