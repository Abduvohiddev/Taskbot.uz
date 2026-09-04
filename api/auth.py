"""
Telegram WebApp initData autentifikatsiyasi
HMAC-SHA256 orqali foydalanuvchini tekshirish.
Token-based auth (Telegram Desktop fallback).
"""
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import parse_qs, unquote

from config import settings

logger = logging.getLogger(__name__)

# ── Token store (xotirada, bir process ichida ishlaydi) ──────────────────────
# {token: {telegram_id, first_name, last_name, username, expires_at}}
_auth_tokens: dict[str, dict] = {}


def create_auth_token(
    telegram_id: int,
    first_name: str = "",
    last_name: str = "",
    username: str = "",
) -> str:
    """5 daqiqalik bir martalik kirish tokeni yaratadi."""
    # Eskirgan tokenlarni tozalash
    now = time.time()
    expired = [k for k, v in _auth_tokens.items() if v["expires_at"] < now]
    for k in expired:
        del _auth_tokens[k]

    token = secrets.token_urlsafe(32)
    _auth_tokens[token] = {
        "telegram_id": telegram_id,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "expires_at": now + 300,  # 5 daqiqa
    }
    return token


def validate_auth_token(token: str) -> dict | None:
    """Token orqali foydalanuvchi ma'lumotini qaytaradi."""
    data = _auth_tokens.get(token)
    if not data:
        return None
    if data["expires_at"] < time.time():
        _auth_tokens.pop(token, None)
        return None
    return {
        "telegram_id": data["telegram_id"],
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "username": data["username"],
        "language_code": "uz",
    }


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
