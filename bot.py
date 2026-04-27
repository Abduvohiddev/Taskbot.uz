"""
TaskBot - Telegram korporativ vazifalar boshqaruvi boti
Asosiy ishga tushirish fayli (Bot + API server)
"""
import asyncio
import logging
import sys
import traceback

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    ErrorEvent, BotCommand, BotCommandScopeDefault,
    MenuButtonWebApp, MenuButtonDefault, WebAppInfo,
)
from redis.asyncio import Redis

from config import settings
from database.db import init_db, close_db
from handlers import start, tasks, groups, stats, admin, common, company, ai_handler, workflow
from middlewares.auth import AuthMiddleware
from middlewares.throttling import ThrottlingMiddleware
from utils.scheduler import setup_scheduler, shutdown_scheduler
from api.server import create_api_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Bot ishga tushganda bajariladigan amallar"""
    logger.info("Bot ishga tushmoqda...")
    await init_db()
    logger.info("Ma'lumotlar bazasi ulandi")

    setup_scheduler(bot)
    logger.info("Scheduler ishga tushdi")

    # Buyruqlar ro'yxatini ro'yxatdan o'tkazish (BotFather da avtomatik ko'rinadi)
    commands = [
        BotCommand(command="start", description="🏠 Botni ishga tushirish"),
        BotCommand(command="app", description="📱 Mini App ochish"),
        BotCommand(command="newtask", description="➕ Yangi vazifa yaratish"),
        BotCommand(command="newworkflow", description="🔗 Ketma-ket workflow vazifa"),
        BotCommand(command="workflows", description="🪜 Mening workflow'larim"),
        BotCommand(command="done", description="✅ Workflow qadamini tugatish"),
        BotCommand(command="mytasks", description="📋 Mening vazifalarim"),
        BotCommand(command="alltasks", description="📑 Barcha vazifalar"),
        BotCommand(command="stats", description="📊 Statistika va chart"),
        BotCommand(command="overdue", description="⏰ Kechikkan vazifalar"),
        BotCommand(command="companies", description="🏢 Kompaniyalarim"),
        BotCommand(command="groups", description="👥 Guruhlarim"),
        BotCommand(command="settings", description="⚙️ Sozlamalar"),
        BotCommand(command="language", description="🌐 Til"),
        BotCommand(command="help", description="❓ Yordam"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Bot buyruqlari ro'yxatga olindi")
    except Exception as e:
        logger.warning(f"Buyruqlarni ro'yxatga olib bo'lmadi: {e}")

    # Chat bar menyu tugmasi — WebApp
    if settings.WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🚀 Ochish",
                    web_app=WebAppInfo(url=settings.WEBAPP_URL),
                )
            )
            logger.info(f"WebApp menu tugma o'rnatildi: {settings.WEBAPP_URL}")
        except Exception as e:
            logger.warning(f"WebApp menu tugmani o'rnatib bo'lmadi: {e}")
    else:
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        except Exception:
            pass

    bot_info = await bot.get_me()
    logger.info(f"Bot @{bot_info.username} muvaffaqiyatli ishga tushdi!")


async def on_shutdown(bot: Bot) -> None:
    """Bot to'xtaganda bajariladigan amallar"""
    logger.info("Bot to'xtamoqda...")
    await shutdown_scheduler()
    await close_db()
    await bot.session.close()
    logger.info("Bot muvaffaqiyatli to'xtadi")


async def main() -> None:
    """Asosiy funksiya - Bot + API server"""
    redis = Redis.from_url(settings.REDIS_URL)
    storage = RedisStorage(redis=redis)
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)
    
    # Global error handler
    @dp.error()
    async def error_handler(event: ErrorEvent):
        """Barcha xatoliklarni ushlash"""
        logger.error(
            f"Update xatolik: {event.exception}\n"
            f"{''.join(traceback.format_exception(type(event.exception), event.exception, event.exception.__traceback__))}"
        )
        try:
            update = event.update
            if update.message:
                await update.message.answer(
                    "❗ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.\n"
                    "Muammo davom etsa /start yuboring."
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    "❗ Xatolik yuz berdi. Qaytadan urining.",
                    show_alert=True,
                )
        except Exception:
            pass
        return True
    
    # Middlewarelar
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # Routerlar — aniq tugma/komanda handlerlari OLDIN, AI fallback ENG OXIRIDA.
    # AI handler `F.text & ~F.text.startswith("/")` bilan barcha matnni tutib oladi,
    # shuning uchun u eng oxirda bo'lishi shart, aks holda "⚙️ Sozlamalar" kabi
    # reply-keyboard tugmalari sozlamalar handleriga yetib bormaydi.
    dp.include_router(start.router)
    dp.include_router(company.router)
    dp.include_router(workflow.router)
    dp.include_router(tasks.router)
    dp.include_router(groups.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)      # ⚙️ Sozlamalar va boshqa aniq matnlar
    dp.include_router(ai_handler.router)  # AI fallback — eng oxirida
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # API server yaratish (bot reference bilan — notifications uchun)
    api_app = create_api_app(bot=bot)
    runner = web.AppRunner(api_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.API_PORT)
    
    try:
        await site.start()
        logger.info(f"API server ishga tushdi: http://0.0.0.0:{settings.API_PORT}")
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await redis.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot foydalanuvchi tomonidan to'xtatildi")
