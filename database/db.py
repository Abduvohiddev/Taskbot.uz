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
                # Masul (responsible): TaskAssignment.is_responsible
                await conn.execute(text(
                    "ALTER TABLE task_assignments ADD COLUMN IF NOT EXISTS is_responsible BOOLEAN DEFAULT FALSE"
                ))
                # Tezlik kuzatuvi: started_at, duration_seconds
                await conn.execute(text(
                    "ALTER TABLE task_assignments ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE"
                ))
                await conn.execute(text(
                    "ALTER TABLE task_assignments ADD COLUMN IF NOT EXISTS duration_seconds INTEGER"
                ))
                # Murojaat admini bayrog'i
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_feedback_admin BOOLEAN DEFAULT FALSE"
                ))
                # Murojaat biriktirmasi — Mini App fayl URL (file_id ixtiyoriy bo'lsin)
                await conn.execute(text(
                    "ALTER TABLE feedback_attachments ADD COLUMN IF NOT EXISTS file_url VARCHAR(500)"
                ))
                await conn.execute(text(
                    "ALTER TABLE feedback_attachments ALTER COLUMN file_id DROP NOT NULL"
                ))
                # Workflow qadam biriktirmasi — Mini App fayl URL
                await conn.execute(text(
                    "ALTER TABLE task_step_attachments ADD COLUMN IF NOT EXISTS file_url VARCHAR(500)"
                ))
                # Admin tomonidan bloklangan guruhlar — bot u yerda umuman ishlamaydi
                await conn.execute(text(
                    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS is_blocked_by_admin BOOLEAN DEFAULT FALSE"
                ))
                # Murojaat javobi — HR panel uchun admin_id null, admin_name/source qo'shildi
                await conn.execute(text(
                    "ALTER TABLE feedback_replies ALTER COLUMN admin_id DROP NOT NULL"
                ))
                await conn.execute(text(
                    "ALTER TABLE feedback_replies ADD COLUMN IF NOT EXISTS admin_name VARCHAR(200)"
                ))
                await conn.execute(text(
                    "ALTER TABLE feedback_replies ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'admin'"
                ))
                # AI maslahatchi — har bir foydalanuvchiga admin yoqadi/o'chiradi
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE"
                ))
                # AI eslatmalar jadvali
                await conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS reminders ("
                    "id BIGSERIAL PRIMARY KEY, "
                    "user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                    "task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE, "
                    "remind_at TIMESTAMP WITH TIME ZONE NOT NULL, "
                    "text TEXT NOT NULL, "
                    "is_sent BOOLEAN DEFAULT FALSE, "
                    "created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), "
                    "sent_at TIMESTAMP WITH TIME ZONE)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_reminders_due ON reminders (remind_at, is_sent)"
                ))
                # HR hujjat kunlik eslatmalari
                await conn.execute(text(
                    "ALTER TABLE hr_documents ADD COLUMN IF NOT EXISTS remind_enabled BOOLEAN DEFAULT FALSE"
                ))
                await conn.execute(text(
                    "ALTER TABLE hr_documents ADD COLUMN IF NOT EXISTS remind_time VARCHAR(5)"
                ))
                await conn.execute(text(
                    "ALTER TABLE hr_assignments ADD COLUMN IF NOT EXISTS last_reminded_on VARCHAR(10)"
                ))
                await conn.execute(text(
                    "ALTER TABLE hr_documents ADD COLUMN IF NOT EXISTS remind_reopen BOOLEAN DEFAULT FALSE"
                ))
                await conn.execute(text(
                    "ALTER TABLE hr_documents ADD COLUMN IF NOT EXISTS remind_interval_days INTEGER DEFAULT 0"
                ))
                await conn.execute(text(
                    "ALTER TABLE hr_documents ADD COLUMN IF NOT EXISTS last_reopen_on VARCHAR(10)"
                ))
                # Workflow qadam — nisbiy muddat (aktivlashgandan N kun)
                await conn.execute(text(
                    "ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS duration_days INTEGER"
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
