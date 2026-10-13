"""
Kod qaysi bo'limniki: polik yoki chexol. Avval 1C dagi vid nomenklatura, vid noma'lum bo'lsa mahsulot nomi.
Natija uc_codes.dept ga yoziladi - dashboard va Google Sheets varaqlari shunga tayanadi.
"""
import re
from typing import Dict, Iterable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from uniccode.config import UnicSettings
from uniccode.models import UCCode, UCProduct

CHEXOL, POLIK = "chexol", "polik"


def category(vid: Optional[str], name: Optional[str], cfg: UnicSettings) -> str:
    """Polik yoki chexol. Qolgan hammasi (torpedka, nakidka...) chexol bo'liminiki."""
    if vid:
        return POLIK if re.search(cfg.UNIC_POLIK_VID_RE, vid, re.I) else CHEXOL
    return POLIK if name and re.search(cfg.UNIC_POLIK_NAME_RE, name, re.I) else CHEXOL


async def assign(session: AsyncSession, cfg: UnicSettings, only_missing: bool = True) -> int:
    """uc_codes.dept ni artikul bo'yicha to'ldiradi. only_missing=False - hammasini qayta hisoblaydi
    (masalan katalog 1C dan yangilangandan keyin). O'zgargan artikullar sonini qaytaradi."""
    q = select(UCCode.article, func.max(UCCode.name)).group_by(UCCode.article)
    if only_missing:
        q = q.where(UCCode.dept.is_(None))
    arts: Dict[str, Optional[str]] = dict((await session.execute(q)).all())
    if not arts:
        return 0
    prods: Dict[str, tuple] = {}
    keys = list(arts)
    for i in range(0, len(keys), 2000):
        rows = (await session.execute(select(UCProduct.article, UCProduct.vid, UCProduct.name)
                                      .where(UCProduct.article.in_(keys[i:i + 2000])))).all()
        prods.update({a: (v, n) for a, v, n in rows})
    by_cat: Dict[str, list] = {CHEXOL: [], POLIK: []}
    for a, code_name in arts.items():
        vid, pname = prods.get(a, (None, None))
        by_cat[category(vid, pname or code_name, cfg)].append(a)
    for cat, items in by_cat.items():
        for chunk in _chunks(items, 2000):
            stmt = update(UCCode).where(UCCode.article.in_(chunk))
            if only_missing:
                stmt = stmt.where(UCCode.dept.is_(None))
            else:
                stmt = stmt.where((UCCode.dept.is_(None)) | (UCCode.dept != cat))
            await session.execute(stmt.values(dept=cat))
    await session.commit()
    return len(arts)


def _chunks(items: list, n: int) -> Iterable[list]:
    for i in range(0, len(items), n):
        yield items[i:i + n]
