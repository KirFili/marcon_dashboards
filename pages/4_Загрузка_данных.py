import calendar
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from core.auth import require_password
from core.db import SessionLocal
from core.ingest import import_sales, import_skus, import_stock_daily
from core.models import StockDaily, Upload
from core.settings import bootstrap_defaults

st.set_page_config(page_title="Загрузка данных", page_icon="📥", layout="wide")
require_password()
bootstrap_defaults()

st.title("Загрузка данных")
st.caption("Выгрузки из 1С: справочник, продажи (помесячно) и дневные остатки.")

MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]


def _save_temp(uploaded) -> str:
    suffix = Path(uploaded.name).suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(uploaded.getvalue())
    tmp.close()
    return tmp.name


def _process(uploaded_files, importer, **kw) -> list[dict]:
    rows = []
    for uf in uploaded_files:
        p = _save_temp(uf)
        try:
            r = importer(p, filename=uf.name, **kw) if "filename" in importer.__code__.co_varnames else importer(p, **kw)
        except Exception as e:  # noqa: BLE001
            r = {"skipped": True, "reason": f"ошибка: {e}"}
        finally:
            os.unlink(p)
        rows.append({
            "Файл": uf.name, "День/итог": r.get("day", "—"),
            "Создано": r.get("created", 0), "Обновлено": r.get("updated", 0),
            "Пропущено (нет SKU)": r.get("skipped_no_sku", 0),
            "Статус": r.get("reason", "ок"),
        })
    st.cache_data.clear()
    return rows


# ---------- Дневные остатки ----------
st.subheader("📅 Дневные остатки (ведомость по товарам)")
st.caption("Можно выбрать сразу много файлов — по одному на день. День берётся из «Период» внутри файла.")

# показать итог прошлой загрузки (после очистки списка файлов)
if "daily_result" in st.session_state:
    res = st.session_state.pop("daily_result")
    loaded = sum(1 for r in res if r["Статус"] == "ок")
    skipped = len(res) - loaded
    msg = f"Загружено файлов: {loaded} из {len(res)}"
    if skipped:
        msg += f" (пропущено: {skipped})"
    st.toast(msg, icon="✅")
    st.success(f"{msg}. Список очищен — можно выбирать новую партию.")
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)

st.session_state.setdefault("daily_key", 0)
daily = st.file_uploader("Дневные ведомости (.xlsx)", type=["xlsx"],
                         accept_multiple_files=True,
                         key=f"daily_{st.session_state['daily_key']}")
if st.button("Загрузить дневные остатки", type="primary", disabled=not daily):
    st.session_state["daily_result"] = _process(daily, import_stock_daily)
    st.session_state["daily_key"] += 1  # новый ключ -> список файлов обнулится
    st.rerun()

# ---------- Календарь покрытия ----------
st.subheader("🗓️ Покрытие по дням")
with SessionLocal() as s:
    days = [d for (d,) in s.execute(select(StockDaily.day).distinct().order_by(StockDaily.day))]
if not days:
    st.info("Дневных остатков пока нет — загрузите ведомости выше.")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Дней с данными", len(days))
    c2.metric("Первый день", str(days[0]))
    c3.metric("Последний день", str(days[-1]))
    cov = {}
    for d in days:
        cov.setdefault((d.year, d.month), set()).add(d.day)
    rows = []
    for (y, m), present in sorted(cov.items()):
        total = calendar.monthrange(y, m)[1]
        missing = sorted(set(range(1, total + 1)) - present)
        rows.append({
            "Месяц": f"{MONTHS_RU[m - 1]} {y}",
            "Покрыто": f"{len(present)}/{total}",
            "Полный": "✅" if not missing else "",
            "Пропущены дни": ", ".join(map(str, missing)) if missing else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()

# ---------- Справочник и продажи ----------
col1, col2 = st.columns(2)
with col1:
    st.subheader("📒 Справочник SKU")
    ref = st.file_uploader("Справочник (.xls/.xlsx)", type=["xls", "xlsx"], key="ref")
    if st.button("Загрузить справочник", disabled=not ref):
        res = _process([ref], import_skus)
        st.toast("Справочник загружен", icon="✅")
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
with col2:
    st.subheader("💰 Продажи (помесячно)")
    sal = st.file_uploader("Отчёт продаж (.xlsx)", type=["xlsx"], key="sales")
    if st.button("Загрузить продажи", disabled=not sal):
        res = _process([sal], import_sales)
        st.toast("Продажи загружены", icon="✅")
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)

st.divider()

# ---------- История загрузок ----------
st.subheader("📜 История загрузок")
with SessionLocal() as s:
    ups = s.scalars(select(Upload).order_by(Upload.uploaded_at.desc()).limit(50)).all()
KIND_RU = {"sku": "справочник", "sales": "продажи", "stock": "остатки (мес)",
           "stock_daily": "остатки (день)"}
hist = pd.DataFrame([
    {"Когда": u.uploaded_at.strftime("%Y-%m-%d %H:%M"), "Тип": KIND_RU.get(u.kind, u.kind),
     "Файл": u.filename, "Строк": u.row_count}
    for u in ups
])
st.dataframe(hist, use_container_width=True, hide_index=True, height=300)
