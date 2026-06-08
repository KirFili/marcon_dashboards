import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "marcon")
_LOGO = Path(__file__).resolve().parent.parent / "assets" / "stardogs_logo.png"


def require_password() -> None:
    if st.session_state.get("authed"):
        return

    col, _ = st.columns([1, 2])
    with col:
        if _LOGO.exists():
            st.image(str(_LOGO), width=240)
    st.title("Аналитические дашборды Маркон")

    # Форма: отправка по кнопке И по Enter в поле пароля.
    with st.form("login", clear_on_submit=False):
        st.caption("Введите пароль для доступа.")
        pwd = st.text_input("Пароль", type="password", label_visibility="collapsed")
        submitted = st.form_submit_button("Войти", type="primary")

    if submitted:
        if pwd == _PASSWORD:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Неверный пароль")

    st.stop()
