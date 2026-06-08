"""Переиспользуемая панель фильтров над таблицами (нативная, в теме)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

# русские подписи для технических имён колонок (чтобы не светить англ. в UI)
_LABELS = {
    "code": "Код 1С", "name": "Наименование", "chamber": "Камера",
    "abc": "ABC", "xyz": "XYZ", "class": "Класс", "repl_status": "Статус",
    "group_kind": "Групировка по видам",
}


def table_filters(
    df: pd.DataFrame,
    key: str,
    search_cols: tuple[str, ...] = (),
    cat_cols: tuple[str, ...] = (),
    expanded: bool = False,
    labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Рисует expander «Фильтры» и возвращает отфильтрованный df.

    - search_cols — колонки, по которым ищем подстроку (поле «Поиск»).
    - cat_cols — категориальные колонки (multiselect по уникальным значениям).
    Каждому виджету нужен уникальный `key` (передавайте разный на каждую таблицу).
    """
    if df.empty or (not search_cols and not cat_cols):
        return df

    lbl = {**_LABELS, **(labels or {})}
    out = df
    n = (1 if search_cols else 0) + len(cat_cols)
    with st.expander("🔎 Фильтры", expanded=expanded):
        cols = st.columns(n)
        i = 0
        if search_cols:
            q = cols[i].text_input("Поиск", key=f"flt_{key}_q",
                                   placeholder="часть названия или кода…")
            i += 1
            if q:
                mask = pd.Series(False, index=out.index)
                for c in search_cols:
                    if c in out:
                        mask |= out[c].astype(str).str.contains(q, case=False, na=False)
                out = out[mask]
        for c in cat_cols:
            if c not in df:
                continue
            opts = sorted(x for x in df[c].dropna().unique())
            sel = cols[i].multiselect(lbl.get(c, c), opts, key=f"flt_{key}_{c}",
                                      placeholder="все")
            i += 1
            if sel:
                out = out[out[c].isin(sel)]

    if len(out) != len(df):
        st.caption(f"Показано **{len(out)}** из {len(df)}.")
    return out
