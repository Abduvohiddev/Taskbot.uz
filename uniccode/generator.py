"""
Kod generatsiyasi. Raqamlar har bir artikul uchun bitta atomar UPSERT bilan band qilinadi,
shuning uchun bir vaqtda bir nechta odam kod so'rasa ham bir xil raqam ikki marta chiqmaydi.
"""
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from uniccode.models import UCBatch, UCCode, UCCounter

ARTICLE_RE = re.compile(r"^\d{6}$")


def normalize_article(value) -> str:
    """'x-844088', 844088.0, ' 844088 ' -> '844088'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    if s.lower().startswith("x-"):
        s = s[2:]
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def date_part(now: datetime) -> str:
    """Kod ichidagi sana qismi: kun + oy (DDMM), Google Sheets'dagi bilan bir xil."""
    return now.strftime("%d%m")


def to_local(d: datetime, tz: str) -> datetime:
    """Bazadan o'qilgan vaqtni mahalliy vaqtga o'tkazadi (sqlite zonasiz qaytaradi - u allaqachon mahalliy)."""
    return d if d.tzinfo is None else d.astimezone(ZoneInfo(tz))


def format_code(article: str, type_code: str, dpart: str, seq: int) -> str:
    return f"{article}{type_code}{dpart}{seq}"


@dataclass
class Item:
    """Kod so'ralgan bitta qator: artikul, soni va qo'shimcha ma'lumot."""
    article: str
    qty: int
    address: Optional[str] = None
    name: Optional[str] = None
    series: Optional[str] = None
    note: Optional[str] = None


@dataclass
class ItemResult:
    item: Item
    codes: List[str] = field(default_factory=list)
    first_seq: int = 0
    last_seq: int = 0


@dataclass
class BatchResult:
    batch_id: int
    created_at: datetime
    items: List[ItemResult]

    @property
    def total(self) -> int:
        return sum(len(r.codes) for r in self.items)


def _insert(session: AsyncSession):
    return postgresql.insert if session.bind.dialect.name == "postgresql" else sqlite.insert


async def reserve(session: AsyncSession, article: str, n: int, start_seq: int) -> int:
    """Artikul uchun n ta ketma-ket raqamni band qiladi va birinchisini qaytaradi."""
    ins = _insert(session)
    stmt = (
        ins(UCCounter)
        .values(article=article, last_seq=start_seq - 1 + n)
        .on_conflict_do_update(
            index_elements=[UCCounter.article],
            set_={"last_seq": UCCounter.last_seq + n, "updated_at": func.now()},
        )
        .returning(UCCounter.last_seq)
    )
    last = (await session.execute(stmt)).scalar_one()
    return int(last) - n + 1


async def generate(
    session: AsyncSession,
    items: Iterable[Item],
    *,
    type_code: str = "CA",
    start_seq: int = 10000000,
    tz: str = "Asia/Tashkent",
    source: str = "kod",
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    filename: Optional[str] = None,
    batch_note: Optional[str] = None,
    now: Optional[datetime] = None,
) -> BatchResult:
    """Qatorlar uchun kod yasaydi, bazaga yozadi va commit qiladi."""
    items = [it for it in items if it.qty > 0]
    for it in items:
        it.article = normalize_article(it.article)
        if not ARTICLE_RE.match(it.article):
            raise ValueError(f"Artikul 6 xonali raqam bo'lishi kerak: {it.article!r}")

    now = now or datetime.now(ZoneInfo(tz))
    dpart = date_part(now)

    batch = UCBatch(user_id=user_id, username=username, source=source, filename=filename, note=batch_note)
    session.add(batch)
    await session.flush()

    # Har bir artikul uchun bitta UPSERT: so'rovdagi barcha qatorlar summasi bir yo'la band qilinadi.
    totals: "OrderedDict[str, int]" = OrderedDict()
    for it in sorted(items, key=lambda x: x.article):  # doim bir xil tartib: deadlock bo'lmaydi
        totals[it.article] = totals.get(it.article, 0) + it.qty
    next_seq = {}
    for art, n in totals.items():
        next_seq[art] = await reserve(session, art, n, start_seq)

    results: List[ItemResult] = []
    rows = []
    for it in items:
        first = next_seq[it.article]
        next_seq[it.article] += it.qty
        res = ItemResult(item=it, first_seq=first, last_seq=first + it.qty - 1)
        for seq in range(first, first + it.qty):
            code = format_code(it.article, type_code, dpart, seq)
            res.codes.append(code)
            rows.append(dict(
                code=code, article=it.article, seq=seq, created_at=now,
                note=it.note if it.note is not None else (it.address or it.series),
                address=it.address, name=it.name, series=it.series,
                batch_id=batch.id, source="bot", synced=False,
            ))
        results.append(res)

    # Katta so'rovlarni bo'laklab yozamiz (asyncpg parametr chegarasi 32767).
    for i in range(0, len(rows), 2500):
        await session.execute(UCCode.__table__.insert(), rows[i:i + 2500])

    batch.count = len(rows)
    await session.commit()
    return BatchResult(batch_id=batch.id, created_at=now, items=results)


async def last_codes(session: AsyncSession, article: str, limit: int = 5):
    article = normalize_article(article)
    counter = await session.get(UCCounter, article)
    q = (
        select(UCCode.code, UCCode.created_at, UCCode.note)
        .where(UCCode.article == article)
        .order_by(UCCode.seq.desc(), UCCode.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    return (counter.last_seq if counter else None), rows
