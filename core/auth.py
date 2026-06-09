import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import func, select

load_dotenv()

_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "marcon")
_LOGO = Path(__file__).resolve().parent.parent / "assets" / "stardogs_logo.png"


def _draft_count() -> int:
    from core.db import SessionLocal
    from core.models import Sku

    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(Sku).where(Sku.is_draft)) or 0


@st.dialog("⚠️ Требуется обновление справочника")
def _drafts_dialog(n: int) -> None:
    st.warning(f"**{n}** новых позиций. Обновите справочник SKU из 1С.")
    if st.button("Понятно", type="primary"):
        st.rerun()


def _maybe_warn_drafts() -> None:
    """Один раз за сессию (после входа) показывает окно, если есть черновики SKU."""
    if st.session_state.get("drafts_warned"):
        return
    st.session_state["drafts_warned"] = True
    n = _draft_count()
    if n > 0:
        _drafts_dialog(n)


def require_password() -> None:
    if st.session_state.get("authed"):
        _maybe_warn_drafts()
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
