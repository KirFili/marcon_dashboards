import pandas as pd
import streamlit as st
from sqlalchemy import select

from core.auth import require_password
from core.db import SessionLocal
from core.inventory import has_pallet_basis
from core.models import Chamber, Sku
from core.settings import bootstrap_defaults, get_setting
from core.sku_fields import OVERRIDABLE, build_ref, effective

st.set_page_config(page_title="Справочник SKU", page_icon="📒", layout="wide")
require_password()
bootstrap_defaults()

st.title("Справочник SKU")
st.caption(
    "Дозаполни/исправь упаковочные данные и единицу хранения. Ручные правки "
    "**фиксируются (🔒) и имеют приоритет над 1С** — новые выгрузки их не "
    "перезаписывают. Чтобы вернуть значение из 1С — отметь «Сбросить к 1С»."
)

UNIT_OPTIONS = ["", "шт", "Коробка", "коробка", "г", "кг", "л", "упак"]
SCOPE = set((get_setting("scope_groups") or "").split(","))

# ---------- загрузка ----------
with SessionLocal() as session:
    chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
    skus = session.scalars(select(Sku).order_by(Sku.group_kind, Sku.name)).all()
    records = []
    for s in skus:
        ref = build_ref(s)
        rec = {
            "id": s.id, "code": s.code, "name": s.name,
            "group_kind": s.group_kind, "chamber": chambers.get(s.chamber_id, ""),
            "unit": effective(s, "unit") or "",
            "units_per_box": effective(s, "units_per_box"),
            "boxes_per_pallet": effective(s, "boxes_per_pallet"),
            "boxes_per_layer": effective(s, "boxes_per_layer"),
            "layers_per_pallet": effective(s, "layers_per_pallet"),
            "units_per_pallet": effective(s, "units_per_pallet"),
            "gap": not has_pallet_basis(ref),
            "locked": bool(s.overrides),
            "reset": False,
            "profile": (s.group_kind or "")[:2] in SCOPE,
        }
        records.append(rec)

df = pd.DataFrame(records)

# ---------- фильтры ----------
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    q = st.text_input("Поиск (код или наименование)", "")
with c2:
    only_profile = st.checkbox("Только профильные", value=True)
with c3:
    only_gaps = st.checkbox("Только с пробелами", value=False)

view = df
if only_profile:
    view = view[view["profile"]]
if only_gaps:
    view = view[view["gap"]]
if q.strip():
    s = q.strip().lower()
    view = view[
        view["code"].str.lower().str.contains(s, na=False)
        | view["name"].str.lower().str.contains(s, na=False)
    ]

m1, m2, m3 = st.columns(3)
m1.metric("Показано SKU", len(view))
m2.metric("С пробелами (в выборке)", int(view["gap"].sum()))
m3.metric("Зафиксировано вручную 🔒", int(df["locked"].sum()))

view = view.reset_index(drop=True)

edited = st.data_editor(
    view,
    num_rows="fixed",
    use_container_width=True,
    height=560,
    column_order=[
        "code", "name", "group_kind", "chamber", "unit", "gap", "locked",
        "units_per_box", "boxes_per_pallet", "boxes_per_layer",
        "layers_per_pallet", "units_per_pallet", "reset",
    ],
    column_config={
        "id": None, "profile": None,
        "code": st.column_config.TextColumn("Код 1С", disabled=True, pinned=True),
        "name": st.column_config.TextColumn("Наименование", disabled=True, width="medium", pinned=True),
        "group_kind": st.column_config.TextColumn("Групировка", disabled=True, pinned=True),
        "chamber": st.column_config.TextColumn("Камера", disabled=True),
        "unit": st.column_config.SelectboxColumn("Ед. хранения", options=UNIT_OPTIONS),
        "gap": st.column_config.CheckboxColumn("Пробел", disabled=True, help="Нельзя посчитать паллеты"),
        "locked": st.column_config.CheckboxColumn("🔒", disabled=True, help="Есть ручная фиксация"),
        "units_per_box": st.column_config.NumberColumn("Штук в коробке", min_value=0, step=1),
        "boxes_per_pallet": st.column_config.NumberColumn("Коробок на паллете", min_value=0, step=1),
        "boxes_per_layer": st.column_config.NumberColumn("Коробов в слое", min_value=0, step=1),
        "layers_per_pallet": st.column_config.NumberColumn("Слоёв на паллете", min_value=0, step=1),
        "units_per_pallet": st.column_config.NumberColumn("Штук на паллете", min_value=0, step=1),
        "reset": st.column_config.CheckboxColumn("Сбросить к 1С", help="Снять все ручные фиксации строки"),
    },
    key="sku_editor",
)

st.caption("⚠️ Сохрани перед сменой фильтров — иначе правки в текущей выборке сбросятся.")


def _norm(field, val):
    if field == "unit":
        return None if (pd.isna(val) or str(val).strip() == "") else str(val).strip()
    return None if pd.isna(val) else int(val)


if st.button("Сохранить", type="primary"):
    locked_cnt = reset_cnt = 0
    with SessionLocal() as session:
        for i, row in edited.iterrows():
            sku = session.get(Sku, int(view.loc[i, "id"]))
            if sku is None:
                continue
            if bool(row["reset"]):
                if sku.overrides:
                    reset_cnt += 1
                sku.overrides = {}
                continue
            ov = {}
            for f in OVERRIDABLE:
                ev = _norm(f, row[f])
                base = getattr(sku, f)
                base = base.lower() if (f == "unit" and isinstance(base, str)) else base
                cmp = ev.lower() if (f == "unit" and isinstance(ev, str)) else ev
                if cmp != base:  # отличается от 1С → фиксируем
                    ov[f] = ev
            sku.overrides = ov
            if ov:
                locked_cnt += 1
        session.commit()
    st.toast(f"Сохранено. Зафиксировано строк: {locked_cnt}, сброшено: {reset_cnt}", icon="✅")
    st.rerun()
