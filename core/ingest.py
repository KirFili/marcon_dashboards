"""Загрузка выгрузок 1С в БД.

Справочник: upsert в `skus` с мерджем «ручное только в пустое» — значение из 1С
побеждает там, где оно есть; где в 1С пусто, остаётся то, что было (в т.ч.
ручные правки). Идемпотентность по hash файла.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import delete, select

from core.db import SessionLocal
from core.inventory import (
    SkuRef,
    chamber_of,
    parse_sales,
    parse_skus,
    parse_stock,
    stock_period,
)
from core.models import Chamber, Sale, Sku, StockDaily, Upload


def file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _int(x: float | None) -> int | None:
    return int(round(x)) if x is not None else None


def _sku_values(ref: SkuRef, chambers: dict[str, int]) -> dict:
    """Поля Sku из SkuRef (None/'' = «нет значения», не перетирает существующее)."""
    return {
        "name": ref.name,
        "group_kind": ref.group_kind,
        "category": ref.group,
        "unit": ref.unit,
        "boxes_per_pallet": _int(ref.boxes_per_pallet),
        "boxes_per_layer": _int(ref.boxes_per_layer),
        "layers_per_pallet": _int(ref.layers_per_pallet),
        "units_per_box": _int(ref.units_per_box),
        "units_per_pallet": _int(ref.units_per_pallet),
        "temp": ref.temp,
        "company": ref.company,
        "chamber_id": chambers.get(chamber_of(ref)),
    }


def import_skus(path: str | Path, *, force: bool = False, session=None) -> dict:
    """Загружает справочник. Возвращает статистику. force=True пропускает
    дедуп по hash (для пере-сохранения из редактора)."""
    own = session is None
    session = session or SessionLocal()
    try:
        h = file_hash(path)
        if not force and session.scalar(select(Upload).where(Upload.file_hash == h)):
            return {"skipped": True, "reason": "файл уже загружен (тот же hash)"}

        refs = parse_skus(path)
        chambers = {c.name: c.id for c in session.scalars(select(Chamber))}
        existing = {s.code: s for s in session.scalars(select(Sku))}

        created = updated = 0
        for code, ref in refs.items():
            vals = _sku_values(ref, chambers)
            sku = existing.get(code)
            if sku is None:
                session.add(Sku(code=code, **vals))
                created += 1
            else:
                for k, v in vals.items():
                    if v not in (None, ""):  # «ручное только в пустое»
                        setattr(sku, k, v)
                updated += 1

        if not force:
            session.add(
                Upload(kind="sku", filename=Path(path).name, file_hash=h,
                       row_count=len(refs))
            )
        session.commit()
        return {"skipped": False, "parsed": len(refs), "created": created,
                "updated": updated}
    finally:
        if own:
            session.close()


def import_sales(
    path: str | Path, *, filename: str | None = None, force: bool = False, session=None
) -> dict:
    """Загружает отчёт продаж в `sales` с ЗАМЕНОЙ ПО МЕСЯЦАМ: для каждого месяца,
    присутствующего в файле, существующие строки этого месяца удаляются и
    записываются заново — данные за месяц = ровно то, что в файле (без
    осиротевших SKU). SKU без кода в справочнике пропускаются (с подсчётом)."""
    own = session is None
    session = session or SessionLocal()
    try:
        h = file_hash(path)
        existing_upload = session.scalar(select(Upload).where(Upload.file_hash == h))
        if existing_upload and not force:
            return {"skipped": True, "reason": "файл уже загружен (тот же hash)"}

        rows = parse_sales(path)
        sku_ids = {s.code: s.id for s in session.scalars(select(Sku))}
        months = sorted({r.period for r in rows})
        upload = existing_upload or Upload(file_hash=h)
        upload.kind = "sales"
        upload.filename = filename or Path(path).name
        upload.row_count = len(rows)
        session.add(upload)
        session.flush()

        # замена по месяцам: чистим существующие строки этих месяцев
        if months:
            session.execute(delete(Sale).where(Sale.period.in_(months)))

        created = skipped_no_sku = 0
        for r in rows:
            sid = sku_ids.get(r.code)
            if sid is None:
                skipped_no_sku += 1
                continue
            session.add(Sale(sku_id=sid, period=r.period, revenue=r.revenue,
                             gross_profit=r.gross_profit, upload_id=upload.id))
            created += 1
        session.commit()
        return {"skipped": False, "parsed": len(rows), "created": created,
                "replaced_months": len(months),
                "months": [str(m) for m in months], "skipped_no_sku": skipped_no_sku}
    finally:
        if own:
            session.close()


def import_stock_daily(
    path: str | Path, *, filename: str | None = None, force: bool = False, session=None
) -> dict:
    """Загружает ОДНУ дневную ведомость в `stock_daily` (день из «Период»
    внутри файла). filename — исходное имя (при загрузке из UI через temp-файл)."""
    own = session is None
    session = session or SessionLocal()
    try:
        h = file_hash(path)
        existing_upload = session.scalar(select(Upload).where(Upload.file_hash == h))
        if existing_upload and not force:
            return {"skipped": True, "reason": "файл уже загружен (тот же hash)"}

        day = stock_period(path)
        if day is None:
            return {"skipped": True, "reason": "не найден период (день) в файле"}
        rows = parse_stock(path)
        sku_ids = {s.code: s.id for s in session.scalars(select(Sku))}
        upload = existing_upload or Upload(file_hash=h)
        upload.kind = "stock_daily"
        upload.filename = filename or Path(path).name
        upload.row_count = len(rows)
        session.add(upload)
        session.flush()

        existing = {
            s.sku_id: s
            for s in session.scalars(select(StockDaily).where(StockDaily.day == day))
        }
        created = updated = skipped_no_sku = 0
        for r in rows:
            sid = sku_ids.get(r.code)
            if sid is None:
                skipped_no_sku += 1
                continue
            st = existing.get(sid)
            if st is None:
                session.add(StockDaily(sku_id=sid, day=day, opening=r.opening,
                                       inbound=r.inbound, outbound=r.outbound,
                                       closing=r.closing, upload_id=upload.id))
                created += 1
            else:
                st.opening, st.inbound = r.opening, r.inbound
                st.outbound, st.closing = r.outbound, r.closing
                st.upload_id = upload.id
                updated += 1
        session.commit()
        return {"skipped": False, "day": str(day), "parsed": len(rows),
                "created": created, "updated": updated, "skipped_no_sku": skipped_no_sku}
    finally:
        if own:
            session.close()
