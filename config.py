"""
Bot sozlamalari - pydantic-settings orqali .env dan o'qiydi
"""
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    BOT_TOKEN: str
    BOT_USERNAME: str = "TaskBot"
    
    DATABASE_URL: str = "postgresql+asyncpg://taskbot:taskbot@localhost:5432/taskbot"
    
    REDIS_URL: str = "redis://localhost:6379/0"
    
    ADMIN_IDS: str = ""
    
    DEFAULT_TIMEZONE: str = "Asia/Tashkent"
    DEFAULT_LANGUAGE: str = "uz"
    
    THROTTLE_RATE: float = 0.5
    
    DEADLINE_WARNING_HOURS: int = 24
    DEADLINE_URGENT_HOURS: int = 1
    DAILY_REPORT_HOUR: int = 9
    
    GROQ_API_KEY: str = ""

    CHART_DPI: int = 130
    CHART_STYLE: str = "seaborn-v0_8-whitegrid"
    
    API_PORT: int = 8080
    WEBAPP_URL: str = ""
    DEBUG: bool = True
    
    @property
    def admin_ids_list(self) -> List[int]:
        """ADMIN_IDS ni list ga aylantirish"""
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
