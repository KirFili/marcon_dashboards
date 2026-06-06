import pandas as pd
import streamlit as st
from sqlalchemy import select

from core.auth import require_password
from core.db import SessionLocal
from core.models import Chamber
from core.settings import bootstrap_defaults, get_setting, set_setting

st.set_page_config(page_title="Настройки", page_icon="⚙️", layout="wide")
require_password()
bootstrap_defaults()

st.title("Настройки")

# ---------- Параметры расчётов ----------
st.subheader("Параметры расчётов")

col1, col2, col3 = st.columns(3)

with col1:
    threshold = st.number_input(
        "Порог хвоста паллеты, %",
        min_value=0,
        max_value=100,
        value=int(get_setting("pallet_tail_threshold_pct") or 10),
        step=1,
        help="Если хвост последней паллеты меньше этого порога, считаем что он впихнут в основное паллетоместо.",
    )

with col2:
    window = st.number_input(
        "Окно индекса мёртвости, дней",
        min_value=1,
        max_value=365,
        value=int(get_setting("dead_window_days") or 90),
        step=1,
        help="За какой период считаем накопленные паллето-дни для рейтинга мёртвых SKU.",
    )

with col3:
    baseline_options = ["year_over_year", "median_profile"]
    current_baseline = get_setting("seasonal_baseline") or "year_over_year"
    baseline_idx = baseline_options.index(current_baseline) if current_baseline in baseline_options else 0
    baseline = st.selectbox(
        "Сезонный baseline",
        baseline_options,
        index=baseline_idx,
        format_func=lambda x: {"year_over_year": "год-к-году", "median_profile": "медианный профиль"}[x],
    )

if st.button("Сохранить параметры", type="primary"):
    set_setting("pallet_tail_threshold_pct", threshold, "int")
    set_setting("dead_window_days", window, "int")
    set_setting("seasonal_baseline", baseline, "str")
    st.toast("Параметры сохранены", icon="✅")

st.divider()

# ---------- Пороги ABC / XYZ ----------
st.subheader("Пороги ABC / XYZ")
st.caption("ABC — по доле накопленной выручки. XYZ — по коэффициенту вариации "
           "(с поправкой на сезон): ниже X — стабильный, ниже Y — умеренный, выше — Z.")
a1, a2, a3, a4 = st.columns(4)
with a1:
    abc_a = st.number_input("ABC: класс A до, %", min_value=1, max_value=99,
                            value=int(get_setting("abc_a_pct") or 80), step=1)
with a2:
    abc_b = st.number_input("ABC: класс B до, %", min_value=1, max_value=100,
                            value=int(get_setting("abc_b_pct") or 95), step=1)
with a3:
    xyz_x = st.number_input("XYZ: класс X до, % (CV)", min_value=1, max_value=200,
                            value=int(get_setting("xyz_x_pct") or 10), step=1)
with a4:
    xyz_y = st.number_input("XYZ: класс Y до, % (CV)", min_value=1, max_value=300,
                            value=int(get_setting("xyz_y_pct") or 25), step=1)

if st.button("Сохранить пороги ABC/XYZ", type="primary"):
    if abc_b <= abc_a:
        st.error("Порог B должен быть больше порога A.")
    elif xyz_y <= xyz_x:
        st.error("Порог Y должен быть больше порога X.")
    else:
        set_setting("abc_a_pct", abc_a, "int")
        set_setting("abc_b_pct", abc_b, "int")
        set_setting("xyz_x_pct", xyz_x, "int")
        set_setting("xyz_y_pct", xyz_y, "int")
        st.toast("Пороги сохранены", icon="✅")

st.divider()

# ---------- Камеры хранения ----------
st.subheader("Камеры хранения")
st.caption(
    "Редактируй ёмкости, температуру, добавляй и удаляй камеры. "
    "После изменений нажми «Сохранить камеры»."
)

with SessionLocal() as session:
    chambers = session.scalars(select(Chamber).order_by(Chamber.sort_order)).all()
    df_initial = pd.DataFrame(
        [
            {
                "id": c.id,
                "name": c.name,
                "temperature_c": c.temperature_c,
                "capacity_pallets": c.capacity_pallets,
                "sort_order": c.sort_order,
                "is_active": c.is_active,
            }
            for c in chambers
        ]
    )

edited = st.data_editor(
    df_initial,
    num_rows="dynamic",
    use_container_width=True,
    height=320,
    column_config={
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "name": st.column_config.TextColumn("Название", required=True),
        "temperature_c": st.column_config.NumberColumn("Температура, °C", format="%.1f"),
        "capacity_pallets": st.column_config.NumberColumn(
            "Ёмкость, паллетомест", min_value=0, step=1
        ),
        "sort_order": st.column_config.NumberColumn("Порядок", min_value=0, step=1),
        "is_active": st.column_config.CheckboxColumn("Активна"),
    },
    key="chambers_editor",
)

if st.button("Сохранить камеры", type="primary"):
    initial_ids = set(df_initial["id"].dropna().astype(int).tolist()) if not df_initial.empty else set()
    edited_ids = set(edited["id"].dropna().astype(int).tolist()) if not edited.empty else set()
    deleted_ids = initial_ids - edited_ids

    with SessionLocal() as session:
        for chamber_id in deleted_ids:
            obj = session.get(Chamber, int(chamber_id))
            if obj is not None:
                session.delete(obj)

        for _, row in edited.iterrows():
            if pd.isna(row.get("name")) or str(row["name"]).strip() == "":
                continue

            row_id = row.get("id")
            if pd.isna(row_id):
                session.add(
                    Chamber(
                        name=str(row["name"]).strip(),
                        temperature_c=float(row.get("temperature_c") or 0),
                        capacity_pallets=int(row.get("capacity_pallets") or 0),
                        sort_order=int(row.get("sort_order") or 0),
                        is_active=bool(row.get("is_active", True)),
                    )
                )
            else:
                obj = session.get(Chamber, int(row_id))
                if obj is None:
                    continue
                obj.name = str(row["name"]).strip()
                obj.temperature_c = float(row.get("temperature_c") or 0)
                obj.capacity_pallets = int(row.get("capacity_pallets") or 0)
                obj.sort_order = int(row.get("sort_order") or 0)
                obj.is_active = bool(row.get("is_active", True))

        session.commit()

    st.toast("Камеры сохранены", icon="✅")
