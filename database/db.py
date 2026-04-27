"""
Ma'lumotlar bazasi ulanish va sessionlar
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker
)

from config import settings
from database.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Jadvallarni yaratish (faqat birinchi marta)"""
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migration: task_assignments ga per-assignee status/completed_at qo'shish
        try:
            dialect = conn.dialect.name
            if dialect == "sqlite":
                res = await conn.execute(text("PRAGMA table_info(task_assignments)"))
                cols = {row[1] for row in res.fetchall()}
                if "status" not in cols:
                    await conn.execute(text(
                        "ALTER TABLE task_assignments ADD COLUMN status VARCHAR(20) DEFAULT 'new'"
                    ))
                if "completed_at" not in cols:
                    await conn.execute(text(
                        "ALTER TABLE task_assignments ADD COLUMN completed_at DATETIME"
                    ))
            else:
                await conn.execute(text(
                    "ALTER TABLE task_assignments ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'new'"
                ))
                await conn.execute(text(
                    "ALTER TABLE task_assignments ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE"
                ))
                # CompanyMember.display_name
                await conn.execute(text(
                    "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS display_name VARCHAR(200)"
                ))
                # Subtask: Task.parent_id
                await conn.execute(text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE"
                ))
        except Exception as e:
            logger.warning(f"Per-assignee status migration skipped: {e}")
    logger.info("Barcha jadvallar yaratildi")


async def close_db() -> None:
    """Ulanishni yopish"""
    await engine.dispose()
    logger.info("DB ulanish yopildi")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Session context manager"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection uchun session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
