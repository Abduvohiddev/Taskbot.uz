"""
Throttling middleware - spam va DDoS dan himoya
"""
import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from cachetools import TTLCache

from config import settings

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Har bir foydalanuvchi uchun so'rovlar tezligini cheklaydi"""
    
    def __init__(self, rate_limit: float = None):
        self.rate_limit = rate_limit or settings.THROTTLE_RATE
        self.cache: TTLCache = TTLCache(maxsize=10_000, ttl=60)
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id
        
        if user_id is None:
            return await handler(event, data)
        
        current_time = time.time()
        last_time = self.cache.get(user_id)
        
        if last_time and (current_time - last_time) < self.rate_limit:
            if isinstance(event, Message):
                await event.answer("⚠️ Iltimos, biroz kutib turing...")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ Juda tez bosyapsiz!", show_alert=False)
            return
        
        self.cache[user_id] = current_time
        return await handler(event, data)
