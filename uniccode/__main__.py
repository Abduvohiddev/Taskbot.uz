"""Ishga tushirish: python -m uniccode"""
import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from uniccode import dept
from uniccode.access import Access
from uniccode.ai import AI
from uniccode.bot import build_dispatcher, onec_sync_forever
from uniccode.config import unic_settings as cfg
from uniccode.db import init_db, make_engine, make_sessionmaker
from uniccode.events import DBLogHandler
from uniccode.notify import Notifier
from uniccode.panel import Panel
from uniccode.sheets_sync import SheetSync

log = logging.getLogger("uniccode")


async def every(seconds: float, fn, name: str, first_delay: float = 5) -> None:
    await asyncio.sleep(first_delay)
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("%s xatosi: %s", name, e)
        await asyncio.sleep(seconds)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not cfg.UNIC_BOT_TOKEN:
        raise SystemExit("UNIC_BOT_TOKEN .env da berilmagan")
    engine = make_engine(cfg.database_url)
    await init_db(engine)
    sm = make_sessionmaker(engine)

    loghandler = DBLogHandler(sm)
    logging.getLogger("uniccode").addHandler(loghandler)
    logging.getLogger("aiogram").addHandler(loghandler)
    tasks = [loghandler.start()]

    access = Access(sm, cfg)
    await access.refresh()
    ai = AI(cfg)
    sync = SheetSync(sm, cfg) if cfg.gsheet_enabled else None
    bot = Bot(cfg.UNIC_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    async def send(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True)

    notifier = Notifier(sm, cfg, access, ai, send)
    panel = Panel(sm, cfg, access, ai, notifier) if cfg.PANEL_ENABLED else None
    dp = build_dispatcher(sm, cfg, sync, access, panel)

    async def assign_missing():
        async with sm() as s:
            await dept.assign(s, cfg, only_missing=True)

    tasks += [
        asyncio.create_task(notifier.run_forever()),
        asyncio.create_task(every(60, access.refresh, "Foydalanuvchilar ro'yxati")),
        asyncio.create_task(every(120, assign_missing, "Bo'lim aniqlash", first_delay=20)),
    ]
    if sync:
        tasks.append(asyncio.create_task(sync.run_forever()))
    if cfg.onec_enabled:
        tasks.append(asyncio.create_task(onec_sync_forever(sm, cfg)))
    runner = None
    if panel:
        runner = web.AppRunner(panel.app(), access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", cfg.PANEL_PORT).start()
        log.info("Admin panel: %s (port %s)", cfg.PANEL_URL or "PANEL_URL yo'q", cfg.PANEL_PORT)
    log.info("AI yordamchi: %s", f"yoqilgan ({cfg.UNIC_AI_MODEL})" if ai.enabled else "o'chiq (ANTHROPIC_API_KEY yo'q)")
    try:
        await dp.start_polling(bot)
    finally:
        for t in tasks:
            t.cancel()
        if runner:
            await runner.cleanup()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
