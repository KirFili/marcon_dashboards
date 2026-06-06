"""Эффективные значения полей SKU: ручная фиксация (overrides) поверх 1С.

Если поле зафиксировано вручную в справочнике дашборда — оно имеет приоритет
над значением из 1С и не перезаписывается импортом.
"""

from __future__ import annotations

from core.inventory import SkuRef
from core.models import Sku

# поля, которые можно фиксировать вручную в редакторе справочника
OVERRIDABLE = [
    "unit", "units_per_box", "boxes_per_pallet", "boxes_per_layer",
    "layers_per_pallet", "units_per_pallet",
]


def effective(sku: Sku, field: str):
    """Значение поля с учётом ручной фиксации (override побеждает 1С)."""
    ov = sku.overrides or {}
    return ov[field] if field in ov else getattr(sku, field)


def build_ref(sku: Sku) -> SkuRef:
    """SkuRef с применёнными ручными фиксациями — для всех расчётов."""
    e = lambda f: effective(sku, f)
    return SkuRef(
        code=sku.code, name=sku.name or "", group_kind=sku.group_kind or "",
        group=sku.category or "", unit=(e("unit") or "").lower(),
        boxes_per_layer=e("boxes_per_layer"), boxes_per_pallet=e("boxes_per_pallet"),
        layers_per_pallet=e("layers_per_pallet"), units_per_box=e("units_per_box"),
        units_per_pallet=e("units_per_pallet"), company=sku.company or "",
        temp=sku.temp or "",
    )
