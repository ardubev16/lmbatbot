from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    TELEGRAM_TOKEN: str = Field(default=...)
    DB_PATH: str = Field(default=":memory:")
    GLOBAL_PVT_NOTIFICATION_USERS: list[tuple[str, int]] = Field(default=[])


@dataclass
class TagGroup:
    group: str
    emojis: str
    tags: list[str]


@dataclass
class WordCount:
    word: str
    count: int


@dataclass
class StudentInfo:
    student_id: int
    name: str
    surname: str
    email: str

    @property
    def fullname(self) -> str:
        return f"{self.name.capitalize()} {self.surname.capitalize()}"
