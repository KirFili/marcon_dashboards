import pandas as pd
import streamlit as st
from sqlalchemy import select

from core.auth import require_password
from core.db import SessionLocal
from core.inventory import SkuRef, has_pallet_basis
from core.models import Chamber, Sku
from core.settings import bootstrap_defaults, get_setting

st.set_page_config(page_title="Справочник SKU", page_icon="📒", layout="wide")
require_password()
bootstrap_defaults()

st.title("Справочник SKU")
st.caption(
    "Дозаполни недостающие упаковочные данные (коробок на паллете, штук в коробке "
    "и т.п.). Поля из 1С (код, наименование, камера) — только для чтения. "
    "При следующей загрузке из 1С ручные правки сохраняются там, где в 1С пусто."
)

# редактируемые упаковочные поля
EDITABLE = [
    "units_per_box", "boxes_per_pallet", "boxes_per_layer",
    "layers_per_pallet", "units_per_pallet",
]
SCOPE = (get_setting("scope_groups") or "").split(",")


def _ref(row: dict) -> SkuRef:
    return SkuRef(
        code=row["code"], name=row["name"] or "", group_kind=row["group_kind"] or "",
        group=row["category"] or "", unit=(row["unit"] or "").lower(),
        boxes_per_layer=row["boxes_per_layer"], boxes_per_pallet=row["boxes_per_pallet"],
        layers_per_pallet=row["layers_per_pallet"], units_per_box=row["units_per_box"],
        units_per_pallet=row["units_per_pallet"], company=row["company"] or "",
        temp=row["temp"] or "",
    )


# ---------- загрузка ----------
with SessionLocal() as session:
    chambers = {c.id: c.name for c in session.scalars(select(Chamber))}
    skus = session.scalars(select(Sku).order_by(Sku.group_kind, Sku.name)).all()
    records = [
        {
            "id": s.id, "code": s.code, "name": s.name,
            "group_kind": s.group_kind, "category": s.category, "unit": s.unit,
            "chamber": chambers.get(s.chamber_id, ""),
            "units_per_box": s.units_per_box, "boxes_per_pallet": s.boxes_per_pallet,
            "boxes_per_layer": s.boxes_per_layer, "layers_per_pallet": s.layers_per_pallet,
            "units_per_pallet": s.units_per_pallet,
        }
        for s in skus
    ]

for r in records:
    ref = _ref({**r, "company": "", "temp": ""})  # company/temp не нужны для пробела
    r["gap"] = not has_pallet_basis(ref)
    r["profile"] = (r["group_kind"] or "")[:2] in SCOPE

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
m3.metric("Профильных всего", int(df["profile"].sum()))

view = view.reset_index(drop=True)

edited = st.data_editor(
    view,
    num_rows="fixed",
    use_container_width=True,
    height=560,
    column_order=[
        "code", "name", "group_kind", "chamber", "unit", "gap",
        "units_per_box", "boxes_per_pallet", "boxes_per_layer",
        "layers_per_pallet", "units_per_pallet",
    ],
    column_config={
        "id": None, "category": None, "profile": None,
        "code": st.column_config.TextColumn("Код 1С", disabled=True),
        "name": st.column_config.TextColumn("Наименование", disabled=True, width="large"),
        "group_kind": st.column_config.TextColumn("Групировка", disabled=True),
        "chamber": st.column_config.TextColumn("Камера", disabled=True),
        "unit": st.column_config.TextColumn("Ед.", disabled=True),
        "gap": st.column_config.CheckboxColumn("Пробел", disabled=True, help="Нельзя посчитать паллеты"),
        "units_per_box": st.column_config.NumberColumn("Штук в коробке", min_value=0, step=1),
        "boxes_per_pallet": st.column_config.NumberColumn("Коробок на паллете", min_value=0, step=1),
        "boxes_per_layer": st.column_config.NumberColumn("Коробов в слое", min_value=0, step=1),
        "layers_per_pallet": st.column_config.NumberColumn("Слоёв на паллете", min_value=0, step=1),
        "units_per_pallet": st.column_config.NumberColumn("Штук на паллете", min_value=0, step=1),
    },
    key="sku_editor",
)

st.caption("⚠️ Сохрани перед сменой фильтров — иначе правки в текущей выборке сбросятся.")

if st.button("Сохранить правки", type="primary"):
    changed = 0
    with SessionLocal() as session:
        for i, row in edited.iterrows():
            sku = session.get(Sku, int(view.loc[i, "id"]))
            if sku is None:
                continue
            for field in EDITABLE:
                new = None if pd.isna(row[field]) else int(row[field])
                old = view.loc[i, field]
                old = None if pd.isna(old) else int(old)
                if new != old:
                    setattr(sku, field, new)
                    changed += 1
        session.commit()
    st.toast(f"Сохранено правок: {changed}", icon="✅")
    st.rerun()
