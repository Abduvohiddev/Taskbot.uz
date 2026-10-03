"""@uniccodebot sozlamalari (.env dan o'qiladi)."""
import base64
import os
from typing import List, Set

from pydantic_settings import BaseSettings, SettingsConfigDict


def _ids(value: str) -> List[int]:
    return [int(x) for x in value.replace(" ", "").split(",") if x]


class UnicSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    UNIC_BOT_TOKEN: str = ""
    # Bo'sh bo'lsa asosiy DATABASE_URL ishlatiladi (jadvallar uc_ prefiksi bilan alohida).
    UNIC_DATABASE_URL: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://taskbot:taskbot@localhost:5432/taskbot"

    # Vergul bilan Telegram ID lar. Ikkalasi ham bo'sh bo'lsa bot hammaga ochiq.
    UNIC_ALLOWED_IDS: str = ""
    UNIC_ADMIN_IDS: str = ""

    UNIC_TYPE_CODE: str = "CA"
    UNIC_START_SEQ: int = 10000000
    UNIC_TZ: str = "Asia/Tashkent"
    # Bitta so'rovda ruxsat etilgan eng ko'p kod soni (xato bilan million kod yasab yubormaslik uchun).
    UNIC_MAX_PER_REQUEST: int = 100000
    # Seriya faylidagi I ustuniga yoziladigan son (shablonda har qatorda 2).
    UNIC_SERIA_I: int = 2

    # 1C OData dan katalogni avtomatik yangilash (ixtiyoriy). Parol faqat serverdagi .env da.
    ONEC_BASE_URL: str = ""
    ONEC_USER: str = ""
    ONEC_PASSWORD: str = ""
    # setup_1c.sh login/parolni base64 da yozadi: apostrof, bo'sh joy, $ kabi belgilar .env da buzilmasligi uchun.
    ONEC_USER_B64: str = ""
    ONEC_PASSWORD_B64: str = ""
    ONEC_SYNC_INTERVAL_HOURS: float = 24

    # Google Sheets sinxronlash (ixtiyoriy). Service account JSON fayl yo'li yoki JSON matnning o'zi.
    GSHEET_ID: str = ""
    GSHEET_WORKSHEET: str = "Kodlar"
    GOOGLE_CREDENTIALS_FILE: str = ""
    GOOGLE_CREDENTIALS_JSON: str = ""
    GSHEET_SYNC_INTERVAL: int = 15
    GSHEET_BATCH: int = 5000

    @property
    def database_url(self) -> str:
        return self.UNIC_DATABASE_URL or self.DATABASE_URL

    @property
    def admin_ids(self) -> Set[int]:
        return set(_ids(self.UNIC_ADMIN_IDS))

    @property
    def allowed_ids(self) -> Set[int]:
        return set(_ids(self.UNIC_ALLOWED_IDS)) | self.admin_ids

    @property
    def onec_user(self) -> str:
        return base64.b64decode(self.ONEC_USER_B64).decode("utf-8") if self.ONEC_USER_B64 else self.ONEC_USER

    @property
    def onec_password(self) -> str:
        return base64.b64decode(self.ONEC_PASSWORD_B64).decode("utf-8") if self.ONEC_PASSWORD_B64 else self.ONEC_PASSWORD

    @property
    def onec_enabled(self) -> bool:
        return bool(self.ONEC_BASE_URL)

    @property
    def gsheet_enabled(self) -> bool:
        """Jadval ID va kalit bo'lsa yoqiladi. Kalit fayli hali qo'yilmagan bo'lsa o'chiq turadi."""
        if not self.GSHEET_ID:
            return False
        if self.GOOGLE_CREDENTIALS_JSON:
            return True
        return bool(self.GOOGLE_CREDENTIALS_FILE) and os.path.isfile(self.GOOGLE_CREDENTIALS_FILE)


unic_settings = UnicSettings()
