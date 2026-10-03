"""
Kiruvchi Excel fayllarni o'qish:
1) 1C "Движения товаров на адресных складах" hisoboti (.xls/.xlsx) - yacheyka bo'yicha qoldiq.
2) Oddiy ro'yxat: Артикул + Кол-во (+ ixtiyoriy Адрес, Наименование, Seria/Партия, Izoh).
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from uniccode.generator import Item, normalize_article

ROW_RE = re.compile(r"^TM_(\d+)[A-Z]", re.I)
CHEXOL_RE = re.compile(r"^(c|cy|x|d|mg|prime)-", re.I)
NOT_CHEXOL = ("nakidka", "nezamerzayka", "antifriz", "torpedka")


def read_rows(path: str) -> List[List]:
    """Birinchi varaqni qatorlar ro'yxati sifatida o'qiydi."""
    if path.lower().endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(path)
        sh = book.sheet_by_index(0)
        return [sh.row_values(i) for i in range(sh.nrows)]
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def is_chexol(name: str) -> bool:
    low = (name or "").lower()
    if any(k in low for k in NOT_CHEXOL):
        return False
    return bool(CHEXOL_RE.match(low))


def row_of(address: str) -> str:
    """TM_9A1 -> '9'; S_TM-Transit -> 'S_TM-Transit' (qatorsiz joylar o'z nomi bilan)."""
    m = ROW_RE.match(address or "")
    return m.group(1) if m else address


# ---------------------------------------------------------------- 1C sklad hisoboti
@dataclass
class StockLine:
    article: str
    name: str
    address: str
    qty: int


@dataclass
class StockReport:
    lines: List[StockLine]
    period: str = ""

    def rows_summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for ln in self.lines:
            if ln.qty > 0:
                k = row_of(ln.address)
                out[k] = out.get(k, 0) + ln.qty
        return out


def parse_stock_report(rows: Sequence[Sequence]) -> Optional[StockReport]:
    hdr_i = None
    for i, r in enumerate(rows[:30]):
        cells = [_s(c) for c in r]
        if "Конечный остаток" in cells and "Адрес" in cells:
            hdr_i = i
            break
    if hdr_i is None:
        return None
    hdr = [_s(c) for c in rows[hdr_i]]
    c_art = hdr.index("Артикул") if "Артикул" in hdr else 0
    c_name = hdr.index("Номенклатура") if "Номенклатура" in hdr else 2
    c_addr = hdr.index("Адрес")
    c_end = hdr.index("Конечный остаток")
    period = ""
    for r in rows[:hdr_i]:
        for c in r:
            if _s(c).startswith(("Период", "Period")):
                period = _s(c)
    lines = []
    for r in rows[hdr_i + 1:]:
        if len(r) <= max(c_addr, c_end):
            continue
        addr = _s(r[c_addr])
        art = normalize_article(r[c_art])
        if not addr or not art or art in ("Итого", "Total"):
            continue
        qty = _num(r[c_end])
        lines.append(StockLine(article=art, name=_s(r[c_name]), address=addr, qty=int(qty or 0)))
    return StockReport(lines=lines, period=period)


def select_lines(report: StockReport, selector: str, only_chexol: bool):
    """selector: '9,1' (qatorlar), 'TM_6D3, S_TM-Transit' (joylar) yoki 'hammasi'.
    Qaytaradi: (tanlangan qatorlar, o'tkazib yuborilgan - qoldig'i 0/manfiy yoki artikuli 6 xonali emas)."""
    parts = [p.strip() for p in re.split(r"[,\s;]+", selector or "") if p.strip()]
    take_all = any(p.lower() in ("hammasi", "all", "barchasi", "*") for p in parts)
    rows = {p for p in parts if p.isdigit()}
    addrs = {p.lower() for p in parts if not p.isdigit()}
    chosen, skipped = [], []
    for ln in report.lines:
        ok = take_all or row_of(ln.address) in rows or ln.address.lower() in addrs
        if not ok or (only_chexol and not is_chexol(ln.name)):
            continue
        valid = ln.qty > 0 and re.match(r"^\d{6}$", ln.article)
        (chosen if valid else skipped).append(ln)
    return chosen, skipped


def stock_items(lines: List[StockLine]) -> List[Item]:
    def key(ln):
        r = row_of(ln.address)
        return (0 if r.isdigit() else 1, int(r) if r.isdigit() else 0, ln.address, ln.article)
    return [Item(article=ln.article, qty=ln.qty, address=ln.address, name=ln.name, note=ln.address)
            for ln in sorted(lines, key=key)]


# ---------------------------------------------------------------- oddiy ro'yxat (seriya bilan)
ALIASES = {
    "article": ("артикул", "artikul", "article", "art"),
    "qty": ("кол-во", "количество", "soni", "miqdor", "qty", "кол", "конечный остаток", "son"),
    "address": ("адрес", "manzil", "yacheyka", "ячейка", "adres"),
    "name": ("наименование", "номенклатура", "nomi", "nomenklatura", "name", "mahsulot"),
    "series": ("seria", "seriya", "серия", "партия", "partiya", "series", "lot"),
    "note": ("izoh", "примечание", "комментарий", "note"),
}


def _match(h: str, field_name: str) -> bool:
    h = h.lower().strip()
    return any(h == a or h.startswith(a) for a in ALIASES[field_name])


@dataclass
class ListFile:
    items: List[Item]
    errors: List[str] = field(default_factory=list)
    columns: Dict[str, int] = field(default_factory=dict)


def parse_list(rows: Sequence[Sequence]) -> Optional[ListFile]:
    hdr_i, cols = None, {}
    for i, r in enumerate(rows[:15]):
        found = {}
        for j, c in enumerate(r):
            h = _s(c)
            if not h:
                continue
            for f in ALIASES:
                if f not in found and _match(h, f):
                    found[f] = j
                    break
        if "article" in found and "qty" in found:
            hdr_i, cols = i, found
            break
    if hdr_i is None:
        # Sarlavhasiz: A = artikul, B = soni, C = seriya/izoh
        if rows and re.match(r"^\d{6}$", normalize_article(rows[0][0] if rows[0] else "")):
            hdr_i, cols = -1, {"article": 0, "qty": 1, "series": 2}
        else:
            return None
    out = ListFile(items=[], columns=cols)
    for n, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
        def g(f):
            j = cols.get(f)
            return r[j] if j is not None and j < len(r) else None
        art = normalize_article(g("article"))
        qty = _num(g("qty"))
        if not art and qty is None:
            continue
        if not re.match(r"^\d{6}$", art):
            if art and art.lower() not in ("итого", "jami", "total"):
                out.errors.append(f"{n}-qator: artikul noto'g'ri ({art})")
            continue
        if qty is None or qty <= 0 or not float(qty).is_integer():
            out.errors.append(f"{n}-qator: soni noto'g'ri ({_s(g('qty'))})")
            continue
        series = _s(g("series")) or None
        note = _s(g("note")) or None
        out.items.append(Item(article=art, qty=int(qty), address=_s(g("address")) or None,
                              name=_s(g("name")) or None, series=series,
                              note=note or series or (_s(g("address")) or None)))
    return out
