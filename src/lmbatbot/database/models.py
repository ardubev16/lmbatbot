from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class TagGroup(Base):
    __tablename__ = "tag_groups"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    group_name: Mapped[str] = mapped_column(primary_key=True)
    tags: Mapped[list[str]] = mapped_column(JSON)
