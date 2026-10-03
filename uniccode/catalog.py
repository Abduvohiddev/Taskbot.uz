"""
Mahsulot katalogi (artikul -> nomenklatura, avto marka).
Har qanday Excel qabul qilinadi: har bir varaqda 'Артикул' va 'Номенклатура'/'Наименование'/'Nomi'
sarlavhali ustunlar qidiriladi; sarlavhasiz varaqda A = artikul, B = nomi deb olinadi.
"""
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from uniccode.generator import normalize_article
from uniccode.models import UCProduct

ART_H = ("артикул", "artikul", "article")
NAME_H = ("номенклатура", "наименование", "nomenklatura", "nomeklatura", "nomi", "name")
MARKA_H = ("марка", "marka", "avto", "mashina")


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _good_name(v) -> bool:
    s = _s(v)
    return bool(s) and s not in ("0", "0.0") and not s.startswith("=")


def _sheets(path: str) -> List[List[list]]:
    if path.lower().endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(path)
        return [[sh.row_values(i) for i in range(sh.nrows)] for sh in book.sheets()]
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
    wb.close()
    return out


def parse_catalog(path: str) -> Dict[str, Tuple[str, Optional[str]]]:
    """Fayldagi barcha varaqlardan {artikul: (nomi, marka)}. Oldingi varaq ustun turadi."""
    found: Dict[str, Tuple[str, Optional[str]]] = {}
    for rows in _sheets(path):
        hdr_i, c_art, c_name, c_marka = None, None, None, None
        for i, r in enumerate(rows[:10]):
            low = [_s(c).lower() for c in r]
            a = next((j for j, h in enumerate(low) if h.startswith(ART_H)), None)
            n = next((j for j, h in enumerate(low) if h.startswith(NAME_H) and "марка" not in h and "avto" not in h), None)
            if a is not None and n is not None:
                hdr_i, c_art, c_name = i, a, n
                c_marka = next((j for j, h in enumerate(low) if any(k in h for k in MARKA_H)), None)
                break
        if hdr_i is None:
            first = next((r for r in rows if r and any(c not in (None, "") for c in r)), None)
            if not first or len(first) < 2 or not re.match(r"^\d{6}$", normalize_article(first[0])):
                continue
            hdr_i, c_art, c_name = -1, 0, 1
        for r in rows[hdr_i + 1:]:
            if len(r) <= max(c_art, c_name):
                continue
            art = normalize_article(r[c_art])
            if not re.match(r"^\d{6}$", art) or not _good_name(r[c_name]) or art in found:
                continue
            marka = _s(r[c_marka]) if c_marka is not None and c_marka < len(r) else ""
            found[art] = (_s(r[c_name])[:255], (marka[:64] or None))
    return found


async def save_catalog(session: AsyncSession, items: Dict[str, Tuple[str, Optional[str]]]) -> int:
    ins = postgresql.insert if session.bind.dialect.name == "postgresql" else sqlite.insert
    data = [dict(article=a, name=n, marka=m) for a, (n, m) in items.items()]
    for i in range(0, len(data), 3000):
        stmt = ins(UCProduct).values(data[i:i + 3000])
        stmt = stmt.on_conflict_do_update(
            index_elements=[UCProduct.article],
            set_={"name": stmt.excluded.name,
                  "marka": func.coalesce(stmt.excluded.marka, UCProduct.marka),
                  "updated_at": func.now()},
        )
        await session.execute(stmt)
    await session.commit()
    return len(data)


async def get_products(session: AsyncSession, articles) -> Dict[str, UCProduct]:
    arts = list({normalize_article(a) for a in articles})
    if not arts:
        return {}
    rows = (await session.execute(select(UCProduct).where(UCProduct.article.in_(arts)))).scalars().all()
    return {p.article: p for p in rows}
