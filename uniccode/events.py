"""
Xatolar jurnali: botdagi WARNING/ERROR loglari uc_events jadvaliga yoziladi (panelda ko'rinadi, Notifier
Telegram'ga yuboradi). Bir xil xabar 30 daqiqa ichida qayta kelsa yangi qator ochilmaydi - count oshadi
(masalan Google ishlamay qolganda har 15 soniyadagi ogohlantirish jurnalni to'ldirib yubormaydi).
"""
import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode.models import UCEvent

SOURCES = {"uniccode.sheets": "sheets", "uniccode.onec": "1c", "uniccode.bot": "bot", "uniccode.ai": "ai",
           "uniccode.panel": "panel", "aiogram": "telegram"}
DEDUP = timedelta(minutes=30)


def source_of(logger_name: str) -> str:
    for prefix, src in SOURCES.items():
        if logger_name == prefix or logger_name.startswith(prefix + "."):
            return src
    return logger_name.split(".")[-1][:32]


async def record(sm: async_sessionmaker, level: str, source: str, message: str, details: Optional[str] = None,
                 user_id: Optional[int] = None) -> int:
    message = (message or "").strip()[:2000] or "(bo'sh xabar)"
    now = datetime.now(timezone.utc)
    async with sm() as s:
        ev = (await s.execute(
            select(UCEvent).where(UCEvent.source == source, UCEvent.message == message, UCEvent.level == level,
                                  UCEvent.last_at >= now - DEDUP).order_by(UCEvent.id.desc()).limit(1)
        )).scalar_one_or_none()
        if ev is not None:
            ev.count += 1
            ev.last_at = now
            if details:
                ev.details = details[:8000]
        else:
            ev = UCEvent(level=level, source=source, message=message, details=(details or None) and details[:8000],
                         user_id=user_id, created_at=now, last_at=now, count=1)
            s.add(ev)
        await s.commit()
        return ev.id


class DBLogHandler(logging.Handler):
    """logging -> navbat -> uc_events. emit() har qanday oqimdan chaqirilishi mumkin, yozish esa event loop'da."""

    def __init__(self, sm: async_sessionmaker, level=logging.WARNING):
        super().__init__(level)
        self.sm = sm
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.queue: Optional[asyncio.Queue] = None

    def start(self) -> asyncio.Task:
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue(maxsize=1000)
        return asyncio.create_task(self._writer())

    def emit(self, record: logging.LogRecord) -> None:
        if self.loop is None or record.name.startswith("uniccode.events") or record.name.startswith("sqlalchemy"):
            return
        try:
            msg = record.getMessage()
            details = "".join(traceback.format_exception(*record.exc_info)) if record.exc_info else None
            item = ("error" if record.levelno >= logging.ERROR else "warning", source_of(record.name), msg, details)
            self.loop.call_soon_threadsafe(self._put, item)
        except Exception:  # log yozish hech qachon botni to'xtatmasin
            pass

    def _put(self, item) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def _writer(self) -> None:
        while True:
            level, source, msg, details = await self.queue.get()
            try:
                await record(self.sm, level, source, msg, details)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.getLogger("uniccode.events").warning("Xatoni jurnalga yozib bo'lmadi: %s", e)
