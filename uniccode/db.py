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
        for table, col, typ in (("uc_codes", "machine", "VARCHAR(64)"), ("uc_products", "vid", "VARCHAR(128)"),
                                ("uc_codes", "dept", "VARCHAR(16)")):
            if conn.dialect.name == "postgresql":
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
            else:
                cols = {r[1] for r in (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()}
                if col not in cols:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
        # Dashboard so'rovlari uchun (mavjud jadvalga create_all indeks qo'shmaydi)
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_uc_codes_created ON uc_codes (created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_uc_codes_dept_created ON uc_codes (dept, created_at)"))
