"""Ulanish va jadvallarni yaratish."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from uniccode.models import UCBase


def make_engine(url: str) -> AsyncEngine:
    kwargs = {"pool_pre_ping": True}
    if not url.startswith("sqlite"):
        kwargs.update(pool_size=5, max_overflow=10, pool_recycle=3600)
    return create_async_engine(url, **kwargs)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(UCBase.metadata.create_all)
        # Keyin qo'shilgan ustunlar (mavjud bazada ham paydo bo'lishi uchun)
        if conn.dialect.name == "postgresql":
            await conn.execute(text("ALTER TABLE uc_codes ADD COLUMN IF NOT EXISTS machine VARCHAR(64)"))
        else:
            cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(uc_codes)"))).fetchall()}
            if "machine" not in cols:
                await conn.execute(text("ALTER TABLE uc_codes ADD COLUMN machine VARCHAR(64)"))
