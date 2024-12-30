from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TagGroupMember(TimestampMixin, Base):
    __tablename__ = "tab_group_members"

    tag_group_id: Mapped[int] = mapped_column(ForeignKey("tag_groups._id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.user_id", ondelete="CASCADE"), primary_key=True)
    added_by_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.user_id"))


class TelegramChat(TimestampMixin, Base):
    __tablename__ = "telegram_chats"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

    tag_groups: Mapped[list[TagGroup]] = relationship()


class TelegramUser(TimestampMixin, Base):
    __tablename__ = "telegram_users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None]
    full_name: Mapped[str | None]

    tag_groups: Mapped[list[TagGroup]] = relationship(secondary=TagGroupMember.__table__, back_populates="users")


class TagGroup(TimestampMixin, Base):
    __tablename__ = "tag_groups"
    __table_args__ = (UniqueConstraint("chat_id", "name"),)

    _id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("telegram_chats.chat_id", ondelete="CASCADE"))
    name: Mapped[str]
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.user_id"))

    users: Mapped[list[TelegramUser]] = relationship(secondary=TagGroupMember.__table__, back_populates="tag_groups")


class UserConfig(TimestampMixin, Base):
    __tablename__ = "users_config"

    chat_id: Mapped[int] = mapped_column(ForeignKey("telegram_chats.chat_id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.user_id", ondelete="CASCADE"), primary_key=True)
    private_notifications: Mapped[bool] = mapped_column(server_default=expression.false())


class WordCounter(Base):
    __tablename__ = "word_counter"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(default=0)


class StudentInfo(Base):
    __tablename__ = "student_info"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    surname: Mapped[str]
    email: Mapped[str]

    @property
    def fullname(self) -> str:
        return f"{self.name.capitalize()} {self.surname.capitalize()}"
