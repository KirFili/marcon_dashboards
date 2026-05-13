import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "marcon")


def require_password() -> None:
    if st.session_state.get("authed"):
        return

    st.title("Marcon Dashboards")
    st.caption("Введите пароль для доступа.")

    pwd = st.text_input("Пароль", type="password", label_visibility="collapsed")
    if st.button("Войти", type="primary"):
        if pwd == _PASSWORD:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Неверный пароль")

    st.stop()
