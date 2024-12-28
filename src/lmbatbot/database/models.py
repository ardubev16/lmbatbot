from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class TagGroup(Base):
    __tablename__ = "tag_groups"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    group_name: Mapped[str] = mapped_column(primary_key=True)
    tags: Mapped[list[str]] = mapped_column(JSON)


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
