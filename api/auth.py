"""
Telegram WebApp initData autentifikatsiyasi
HMAC-SHA256 orqali foydalanuvchini tekshirish
"""
import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs, unquote

from config import settings

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str) -> dict | None:
    """
    Telegram WebApp initData ni tekshirish va foydalanuvchi ma'lumotlarini qaytarish.
    
    Returns:
        dict with user info if valid, None otherwise
    """
    if not init_data:
        return None
    
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        
        # hash ni ajratib olish
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None
        
        # data-check-string yaratish (hash ni olib tashlab, alifbo tartibida)
        data_pairs = []
        for key, values in parsed.items():
            if key == "hash":
                continue
            data_pairs.append(f"{key}={values[0]}")
        
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)
        
        # HMAC-SHA256 hisoblash
        secret_key = hmac.new(
            b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(computed_hash, received_hash):
            logger.warning("WebApp initData hash mos kelmadi")
            return None
        
        # User ma'lumotlarini olish
        user_data_str = parsed.get("user", [None])[0]
        if not user_data_str:
            return None
        
        user_data = json.loads(unquote(user_data_str))
        
        return {
            "telegram_id": user_data.get("id"),
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", ""),
            "username": user_data.get("username", ""),
            "language_code": user_data.get("language_code", "uz"),
        }
    except Exception as e:
        logger.exception(f"initData validatsiya xatosi: {e}")
        return None
