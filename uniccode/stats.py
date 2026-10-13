"""Dashboard va kunlik hisobot uchun raqamlar. dept=None - hammasi, 'chexol'/'polik' - bitta bo'lim."""
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uniccode.models import UCBatch, UCCode, UCEvent, UCProduct


def _local_date(col, dialect: str, tz: str):
    if dialect == "postgresql":
        return func.date(func.timezone(tz, col))
    return func.date(col)  # sqlite: vaqt mahalliy holda saqlanadi


async def dashboard(session: AsyncSession, tz: str, dept: Optional[str] = None, days: int = 30) -> dict:
    dialect = session.bind.dialect.name
    zone = ZoneInfo(tz)
    now = datetime.now(zone)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - timedelta(days=days - 1)
    if dialect != "postgresql":           # sqlite zonasiz vaqt saqlaydi
        today, since = today.replace(tzinfo=None), since.replace(tzinfo=None)

    def scoped(q):
        return q.where(UCCode.dept == dept) if dept else q

    async def count(q):
        return (await session.execute(scoped(q))).scalar_one()

    base = select(func.count()).select_from(UCCode)
    totals = {
        "jami": await count(base),
        "bugun": await count(base.where(UCCode.created_at >= today)),
        "7_kun": await count(base.where(UCCode.created_at >= today - timedelta(days=6))),
        f"{days}_kun": await count(base.where(UCCode.created_at >= since)),
        "artikullar": await count(select(func.count(func.distinct(UCCode.article))).select_from(UCCode)),
    }
    by_dept = dict((await session.execute(
        select(UCCode.dept, func.count()).where(UCCode.created_at >= since).group_by(UCCode.dept))).all())

    day = _local_date(UCCode.created_at, dialect, tz).label("d")
    daily_rows = (await session.execute(scoped(
        select(day, UCCode.dept, func.count()).where(UCCode.created_at >= since).group_by(day, UCCode.dept)))).all()
    labels = [(since + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    series = {"chexol": [0] * days, "polik": [0] * days, None: [0] * days}
    idx = {d: i for i, d in enumerate(labels)}
    for d, dp, n in daily_rows:
        i = idx.get(str(d)[:10])
        if i is not None:
            series[dp if dp in series else None][i] += n

    top_articles = [
        {"artikul": a, "nomi": nm or "", "kodlar": n}
        for a, nm, n in (await session.execute(scoped(
            select(UCCode.article, func.max(UCProduct.name), func.count().label("n"))
            .outerjoin(UCProduct, UCProduct.article == UCCode.article)
            .where(UCCode.created_at >= since).group_by(UCCode.article).order_by(func.count().desc()).limit(10)
        ))).all()
    ]
    top_users = [
        {"user_id": uid, "username": un or "", "kodlar": n, "sorovlar": b}
        for uid, un, n, b in (await session.execute(scoped(
            select(UCBatch.user_id, func.max(UCBatch.username), func.count(UCCode.id),
                   func.count(func.distinct(UCBatch.id)))
            .join(UCBatch, UCBatch.id == UCCode.batch_id)
            .where(UCCode.created_at >= since, UCBatch.source != "import")
            .group_by(UCBatch.user_id).order_by(func.count(UCCode.id).desc()).limit(10)
        ))).all()
    ]
    recent = [
        {"id": bid, "vaqt": ts, "user_id": uid, "username": un or "", "manba": src, "fayl": fn or "", "kodlar": n}
        for bid, ts, uid, un, src, fn, n in (await session.execute(scoped(
            select(UCBatch.id, UCBatch.created_at, UCBatch.user_id, UCBatch.username, UCBatch.source,
                   UCBatch.filename, func.count(UCCode.id))
            .join(UCCode, UCCode.batch_id == UCBatch.id)
            .group_by(UCBatch.id).order_by(UCBatch.id.desc()).limit(15)
        ))).all()
    ]
    no_vid = (await session.execute(
        select(func.count(func.distinct(UCCode.article))).select_from(UCCode)
        .outerjoin(UCProduct, UCProduct.article == UCCode.article)
        .where(UCCode.created_at >= since, UCProduct.vid.is_(None)))).scalar_one()
    errors_24h = (await session.execute(
        select(func.count()).select_from(UCEvent)
        .where(UCEvent.level == "error", UCEvent.last_at >= now - timedelta(hours=24)))).scalar_one()
    pending = (await session.execute(
        select(func.count()).select_from(UCCode).where(UCCode.synced.is_(False)))).scalar_one()
    return {
        "bolim": dept or "hammasi", "sana": now.strftime("%d.%m.%Y %H:%M"), "jami": totals,
        "bolimlar_30_kun": {k or "aniqlanmagan": v for k, v in by_dept.items()},
        "kunlik": {"labels": labels, "chexol": series["chexol"], "polik": series["polik"],
                   "aniqlanmagan": series[None]},
        "top_artikullar": top_articles, "top_foydalanuvchilar": top_users, "oxirgi_sorovlar": recent,
        "vidsiz_artikullar_30_kun": no_vid, "xatolar_24_soat": errors_24h, "sheets_kutilmoqda": pending,
    }
