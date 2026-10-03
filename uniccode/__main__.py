"""Ishga tushirish: python -m uniccode"""
import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from uniccode.bot import build_dispatcher, onec_sync_forever
from uniccode.config import unic_settings as cfg
from uniccode.db import init_db, make_engine, make_sessionmaker
from uniccode.sheets_sync import SheetSync


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not cfg.UNIC_BOT_TOKEN:
        raise SystemExit("UNIC_BOT_TOKEN .env da berilmagan")
    engine = make_engine(cfg.database_url)
    await init_db(engine)
    sm = make_sessionmaker(engine)
    sync = SheetSync(sm, cfg) if cfg.gsheet_enabled else None
    bot = Bot(cfg.UNIC_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(sm, cfg, sync)
    tasks = [asyncio.create_task(sync.run_forever())] if sync else []
    if cfg.onec_enabled:
        tasks.append(asyncio.create_task(onec_sync_forever(sm, cfg)))
    try:
        await dp.start_polling(bot)
    finally:
        for t in tasks:
            t.cancel()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
