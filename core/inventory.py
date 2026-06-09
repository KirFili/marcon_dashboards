"""Парсинг выгрузок 1С и расчёт паллетомест для дашборда товарооборота.

Без БД и Streamlit — чистые функции, чтобы их можно было тестировать и
переиспользовать в загрузчике и метриках.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# --- параметры расчёта (дефолты; в проде берутся из settings) ---
TAIL_THRESHOLD = 0.10  # порог хвоста паллеты
WEIGHT_CAP = 300.0  # кг или л на паллету для весовых/наливных

# профильные группы (поле «Групировка по Видам Номенклатуры»), по префиксу-номеру
PROFILE_GROUP_PREFIXES = ("30", "31", "32", "33", "34", "25", "16", "27", "21", "22")

# единицы хранения
BOX_UNITS = {"коробка"}
PIECE_UNITS = {"шт"}
WEIGHT_UNITS = {"г": 0.001, "кг": 1.0, "л": 1.0}  # -> кг / л


# ----------------------------------------------------------------------------
# Чтение xls/xlsx в единую сетку строк (list[list[str]])
# ----------------------------------------------------------------------------
def _read_grid(path: str | Path) -> list[list[str]]:
    path = Path(path)
    if path.suffix.lower() == ".xls":
        import xlrd

        sh = xlrd.open_workbook(str(path)).sheet_by_index(0)
        grid = []
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                v = sh.cell_value(r, c)
                row.append("" if v in (None, "") else str(v).strip())
            grid.append(row)
        return grid
    import openpyxl

    ws = openpyxl.load_workbook(str(path), read_only=True, data_only=True).active
    grid = []
    for row in ws.iter_rows(values_only=True):
        grid.append(["" if v in (None, "") else str(v).strip() for v in row])
    return grid


def _to_float(s: str) -> float | None:
    """Положительное число или None (для количеств/упаковки)."""
    if not s:
        return None
    try:
        x = float(s.replace(",", ".").replace(" ", ""))
        return x if x > 0 else None
    except ValueError:
        return None


def _to_signed(s: str) -> float | None:
    """Любое число (деньги: прибыль/возвраты могут быть отрицательными)."""
    if not s:
        return None
    try:
        return float(s.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# Справочник SKU
# ----------------------------------------------------------------------------
# точные подписи колонок 1С -> ключ в SkuRef
_SKU_COLS = {
    "Код 1С": "code",
    "Номенклатура": "name",
    "Номенклатура.Групировка по Видам Номенклатуры (Общие)": "group_kind",
    "Номенклатура.Группа": "group",
    "Номенклатура.Единица хранения": "unit",
    "Номенклатура.Количество коробов в слое: (Общие)": "boxes_per_layer",
    "Номенклатура.Количество коробов на паллете: (Общие)": "boxes_per_pallet",
    "Номенклатура.Количество слоев на паллете: (Общие)": "layers_per_pallet",
    "Номенклатура.КомпанияОтгрузки (Общие)": "company",
    "Номенклатура.ТемпературныйРежим": "temp",
    "Номенклатура.Штук в коробке (Общие)": "units_per_box",
    "Номенклатура.Штук на паллете (Общие)": "units_per_pallet",
}


@dataclass
class SkuRef:
    code: str
    name: str = ""
    group_kind: str = ""  # Групировка по видам (для скоупа)
    group: str = ""  # Группа (категория)
    unit: str = ""  # единица хранения (lower)
    boxes_per_layer: float | None = None
    boxes_per_pallet: float | None = None
    layers_per_pallet: float | None = None
    units_per_box: float | None = None
    units_per_pallet: float | None = None
    company: str = ""
    temp: str = ""


def parse_skus(path: str | Path) -> dict[str, SkuRef]:
    """Справочник -> {Код 1С: SkuRef}. Пропускает преамбулу и группировочные
    строки (у группы пуст «Наименование»)."""
    grid = _read_grid(path)
    hdr_idx = next(i for i, row in enumerate(grid[:15]) if "Код 1С" in row)
    header = grid[hdr_idx]
    col = {name: header.index(cap) for cap, name in _SKU_COLS.items() if cap in header}

    def cell(row, key):
        i = col.get(key)
        return row[i] if (i is not None and i < len(row)) else ""

    refs: dict[str, SkuRef] = {}
    num_keys = {
        "boxes_per_layer", "boxes_per_pallet", "layers_per_pallet",
        "units_per_box", "units_per_pallet",
    }
    for row in grid[hdr_idx + 1 :]:
        code = cell(row, "code")
        name = cell(row, "name")
        if not code or not name:  # преамбула / группировочная строка
            continue
        kw = {}
        for key in _SKU_COLS.values():
            if key in ("code",):
                continue
            v = cell(row, key)
            if key in num_keys:
                kw[key] = _to_float(v)
            elif key == "unit":
                kw[key] = v.lower()
            else:
                kw[key] = v
        refs[code] = SkuRef(code=code, **kw)
    return refs


# ----------------------------------------------------------------------------
# Отчёт остатков (ведомость по товарам)
# ----------------------------------------------------------------------------
@dataclass
class StockRow:
    code: str
    name: str
    opening: float
    inbound: float
    outbound: float
    closing: float


def stock_period(path: str | Path) -> date | None:
    """Точная дата НАЧАЛА периода ведомости из «Период: dd.mm.yyyy - ...».
    Для дневного отчёта (начало==конец) это и есть нужный день; для месячного —
    1-е число месяца."""
    grid = _read_grid(path)
    for row in grid[:10]:
        for cell in row:
            if cell.startswith("Период"):
                m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", cell)
                if m:
                    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def parse_stock(path: str | Path) -> list[StockRow]:
    """Ведомость -> список движений. Колонки находим по подписям
    «Начальный остаток / Приход / Расход / Конечный остаток»."""
    grid = _read_grid(path)
    sub_idx = next(i for i, row in enumerate(grid) if "Начальный остаток" in row)
    sub = grid[sub_idx]
    c_open = sub.index("Начальный остаток")
    c_in = sub.index("Приход")
    c_out = sub.index("Расход")
    c_close = sub.index("Конечный остаток")
    head = grid[sub_idx - 1]
    c_code = head.index("Код")
    c_name = head.index("Номенклатура")

    def num(row, i):
        return _to_float(row[i]) or 0.0 if i < len(row) else 0.0

    rows: list[StockRow] = []
    for row in grid[sub_idx + 1 :]:
        name = row[c_name] if c_name < len(row) else ""
        if not name:
            continue
        rows.append(
            StockRow(
                code=row[c_code] if c_code < len(row) else "",
                name=name,
                opening=num(row, c_open),
                inbound=num(row, c_in),
                outbound=num(row, c_out),
                closing=num(row, c_close),
            )
        )
    return rows


# ----------------------------------------------------------------------------
# Скоуп и камеры
# ----------------------------------------------------------------------------
def is_profile(ref: SkuRef, prefixes=PROFILE_GROUP_PREFIXES) -> bool:
    return ref.group_kind[:2] in prefixes


def chamber_of(ref: SkuRef) -> str:
    """Привязка SKU к камере. Сухие (Темп 20+) и пустой темп -> Охлаждёнка."""
    t = ref.temp
    if t == "-18С":
        return "Заморозка СД" if ref.company == "СД" else "Заморозка ТП+ОБЩ"
    return "Охлажденка"  # +2..+6, Темп 20+, пусто


# ----------------------------------------------------------------------------
# Расчёт паллет (с фолбэками)
# ----------------------------------------------------------------------------
def boxes_per_pallet(ref: SkuRef) -> tuple[float | None, str]:
    if ref.boxes_per_pallet:
        return ref.boxes_per_pallet, "прямое"
    if ref.boxes_per_layer and ref.layers_per_pallet:
        return ref.boxes_per_layer * ref.layers_per_pallet, "слой×слоёв"
    if ref.units_per_pallet and ref.units_per_box:
        return ref.units_per_pallet / ref.units_per_box, "штук-паллету÷штук-коробке"
    return None, ""


def units_per_pallet(ref: SkuRef) -> tuple[float | None, str]:
    # «Штук на паллете» [126] в 1С часто недостоверно (≠ штук-коробке×коробов-паллете,
    # расхождение до 10-25×), поэтому СНАЧАЛА считаем через коробки.
    bpp, _ = boxes_per_pallet(ref)
    if bpp and ref.units_per_box:
        return bpp * ref.units_per_box, "коробов-паллету×штук-коробке"
    if ref.units_per_pallet:
        return ref.units_per_pallet, "прямое [126]"
    return None, ""


def occupancy_slots(ref: SkuRef, qty: float) -> int | None:
    """Занятые паллетоместа для остатка `qty` (в единице хранения SKU)."""
    unit = ref.unit
    if unit in BOX_UNITS:
        cap, _ = boxes_per_pallet(ref)
        return slots(qty, cap)
    if unit in PIECE_UNITS:
        cap, _ = units_per_pallet(ref)
        return slots(qty, cap)
    if unit in WEIGHT_UNITS:
        return slots(qty * WEIGHT_UNITS[unit], WEIGHT_CAP)
    return None


def has_pallet_basis(ref: SkuRef) -> bool:
    """Можно ли посчитать паллеты по SKU (с учётом единицы и фолбэков)."""
    if ref.unit in WEIGHT_UNITS:
        return True
    if ref.unit in BOX_UNITS:
        return boxes_per_pallet(ref)[0] is not None
    if ref.unit in PIECE_UNITS:
        return units_per_pallet(ref)[0] is not None
    return False


def slots(amount: float, capacity: float | None, threshold=TAIL_THRESHOLD) -> int | None:
    """Паллетоместа: целое с порогом хвоста."""
    if not capacity or capacity <= 0:
        return None
    if amount <= 0:
        return 0
    full = int(amount // capacity)
    tail = (amount - full * capacity) / capacity
    if full == 0:
        return 1
    return full + 1 if tail > threshold else full


@dataclass
class PalletCalc:
    """Результат расчёта паллет по одной позиции отчёта."""
    opening_slots: int | None = None
    inbound_pallets: float | None = None
    outbound_pallets: float | None = None
    closing_slots: int | None = None
    closing_boxes: int | None = None
    note: str = ""
    chamber: str = ""


def compute_pallets(ref: SkuRef | None, row: StockRow) -> PalletCalc:
    """Считает паллеты по позиции отчёта с учётом единицы и фолбэков."""
    res = PalletCalc()
    if ref is None:
        res.note = "Код 1С нет в справочнике"
        return res
    res.chamber = chamber_of(ref)
    unit = ref.unit
    notes: list[str] = []

    if unit in BOX_UNITS or unit in PIECE_UNITS:
        if unit in BOX_UNITS:
            cap, src = boxes_per_pallet(ref)
            amount = lambda q: q  # количество уже в коробках
            box_of = lambda q: q
        else:  # шт
            cap, src = units_per_pallet(ref)
            amount = lambda q: q
            box_of = lambda q: (q / ref.units_per_box if ref.units_per_box else None)
        if cap is None:
            res.note = "не хватает данных для паллет (нет коробов/штук на паллете)"
            return res
        res.opening_slots = slots(amount(row.opening), cap)
        res.closing_slots = slots(amount(row.closing), cap)
        res.inbound_pallets = round(amount(row.inbound) / cap, 2)
        res.outbound_pallets = round(amount(row.outbound) / cap, 2)
        b = box_of(row.closing)
        res.closing_boxes = round(b) if b is not None else None
        if src != "прямое":
            notes.append(f"коробов/паллету расчётно ({src})")
    elif unit in WEIGHT_UNITS:
        k = WEIGHT_UNITS[unit]
        res.opening_slots = slots(row.opening * k, WEIGHT_CAP)
        res.closing_slots = slots(row.closing * k, WEIGHT_CAP)
        res.inbound_pallets = round(row.inbound * k / WEIGHT_CAP, 2)
        res.outbound_pallets = round(row.outbound * k / WEIGHT_CAP, 2)
        notes.append(f"весовой/наливной: паллета={WEIGHT_CAP:g} {'л' if unit == 'л' else 'кг'}")
    else:
        res.note = f"ед. «{ref.unit}» не переводится в паллеты"
        return res

    res.note = "; ".join(notes)
    return res


# ----------------------------------------------------------------------------
# Отчёт о продажах (помесячный кросс-таб: выручка/валовая прибыль по SKU×месяц)
# ----------------------------------------------------------------------------
@dataclass
class SaleRow:
    code: str
    period: date  # первое число месяца
    revenue: float
    gross_profit: float
    name: str = ""


def _month_date(s: str) -> date:
    d, m, y = s.split(".")
    return date(int(y), int(m), 1)


def parse_sales(path: str | Path) -> list[SaleRow]:
    """Кросс-таб «Выручка по контрагентам» -> строки SKU×месяц.

    Шапка: строка с «Номенклатура, Код» (даты месяцев, порядок произвольный),
    следующая строка — метрики (Выручка / Валовая прибыль / Рентабельность).
    Колонка SKU: «<наименование>, <Код 1С>» — код после последней запятой.
    """
    grid = _read_grid(path)
    hdr = next(i for i, row in enumerate(grid) if row and row[0].startswith("Номенклатура"))
    dates, metrics = grid[hdr], grid[hdr + 1]
    rev_col: dict[str, int] = {}
    gp_col: dict[str, int] = {}
    cur = ""
    for c in range(max(len(dates), len(metrics))):
        d = dates[c] if c < len(dates) else ""
        if d:
            cur = d
        m = metrics[c] if c < len(metrics) else ""
        if cur and cur != "Итого":
            if m == "Выручка":
                rev_col[cur] = c
            elif m == "Валовая прибыль":
                gp_col[cur] = c
    months = sorted(rev_col, key=lambda s: (s[6:10], s[3:5]))

    rows: list[SaleRow] = []
    for row in grid[hdr + 2 :]:
        nc = row[0] if row else ""
        if not nc or "," not in nc:  # пусто / группировочная строка
            continue
        name, code = (s.strip() for s in nc.rsplit(",", 1))  # «<имя>, <Код 1С>»
        for mn in months:
            rev = _to_signed(row[rev_col[mn]]) if rev_col[mn] < len(row) else None
            gp = _to_signed(row[gp_col[mn]]) if (mn in gp_col and gp_col[mn] < len(row)) else None
            if rev is None and gp is None:
                continue
            rows.append(SaleRow(code, _month_date(mn), rev or 0.0, gp or 0.0, name=name))
    return rows
