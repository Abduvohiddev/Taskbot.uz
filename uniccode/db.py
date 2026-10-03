"""Ulanish va jadvallarni yaratish."""
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
