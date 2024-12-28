from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    TELEGRAM_TOKEN: str = Field(default=...)
    DB_URL: str = Field(default="sqlite://")
    GLOBAL_PVT_NOTIFICATION_USERS: list[tuple[str, int]] = Field(default=[])


settings = Settings()
