"""@uniccodebot sozlamalari (.env dan o'qiladi)."""
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
    def gsheet_enabled(self) -> bool:
        return bool(self.GSHEET_ID and (self.GOOGLE_CREDENTIALS_FILE or self.GOOGLE_CREDENTIALS_JSON))


unic_settings = UnicSettings()
