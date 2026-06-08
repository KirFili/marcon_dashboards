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
from core.models import Sale, Sku, StockDaily, Upload
from core.settings import bootstrap_defaults

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


def _process(uploaded_files, importer) -> list[dict]:
    rows = []
    for uf in uploaded_files:
        p = _save_temp(uf)
        try:
            if "filename" in importer.__code__.co_varnames:
                r = importer(p, filename=uf.name)
            else:
                r = importer(p)
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


def _result_block(state_key: str) -> None:
    """Показывает итог прошлой загрузки (toast + баннер + таблица) и очищает его."""
    rk = f"{state_key}_result"
    if rk not in st.session_state:
        return
    res = st.session_state.pop(rk)
    loaded = sum(1 for r in res if r["Статус"] == "ок")
    skipped = len(res) - loaded
    msg = f"Загружено: {loaded} из {len(res)}" + (f" (пропущено: {skipped})" if skipped else "")
    st.toast(msg, icon="✅")
    st.success(f"{msg}. Список очищен — можно выбирать новые файлы.")
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)


def _uploader_block(state_key, label, types, importer, button_label, *, multiple, primary=False):
    """Загрузчик с динамическим ключом: после загрузки список обнуляется."""
    kk = f"{state_key}_key"
    st.session_state.setdefault(kk, 0)
    files = st.file_uploader(label, type=types, accept_multiple_files=multiple,
                             key=f"{state_key}_{st.session_state[kk]}")
    if st.button(button_label, type="primary" if primary else "secondary", disabled=not files):
        ufs = files if multiple else [files]
        st.session_state[f"{state_key}_result"] = _process(ufs, importer)
        st.session_state[kk] += 1  # новый ключ -> список файлов обнулится
        st.rerun()


# ---------- Дневные остатки ----------
st.subheader("📅 Дневные остатки (ведомость по товарам)")
st.caption("Можно выбрать сразу много файлов — по одному на день. День берётся из «Период» внутри файла.")
_result_block("daily")
_uploader_block("daily", "Дневные ведомости (.xlsx)", ["xlsx"], import_stock_daily,
                "Загрузить дневные остатки", multiple=True, primary=True)

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
    _result_block("ref")
    _uploader_block("ref", "Справочник (.xls/.xlsx)", ["xls", "xlsx"], import_skus,
                    "Загрузить справочник", multiple=False)
    with SessionLocal() as s:
        last = s.scalar(select(Upload).where(Upload.kind == "sku")
                        .order_by(Upload.uploaded_at.desc()))
        n_sku = s.scalar(select(func.count()).select_from(Sku))
    if last:
        st.info(f"🕒 Последнее обновление: **{last.uploaded_at.strftime('%Y-%m-%d %H:%M')}** · "
                f"SKU в базе: **{n_sku}** · файл: {last.filename}")
    else:
        st.warning("Справочник ещё не загружался.")

with col2:
    st.subheader("💰 Продажи (помесячно)")
    _result_block("sales")
    _uploader_block("sales", "Отчёт продаж (.xlsx)", ["xlsx"], import_sales,
                    "Загрузить продажи", multiple=False)
    with SessionLocal() as s:
        months = sorted({p for (p,) in s.execute(select(Sale.period).distinct())})
    if months:
        labels = [f"{MONTHS_RU[m.month - 1]} {m.year}" for m in months]
        st.info(f"📆 Загружены месяцы (**{len(months)}**): {labels[0]} … {labels[-1]}")
        with st.expander("Все месяцы продаж"):
            st.write(", ".join(labels))
    else:
        st.warning("Продажи ещё не загружались.")

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
