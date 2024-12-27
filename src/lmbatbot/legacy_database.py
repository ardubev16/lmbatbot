from __future__ import annotations

import functools
import sqlite3
from enum import Enum, auto
from typing import TYPE_CHECKING, Concatenate

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lmbatbot.models import StudentInfo
from lmbatbot.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable

engine = create_engine(settings.DB_URL)

Session = sessionmaker(engine)


class UpsertResult(Enum):
    INSERTED = auto()
    UPDATED = auto()


class DeleteResult(Enum):
    DELETED = auto()
    NOT_FOUND = auto()


class DbHelper:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)

    def create_tables(self) -> None:
        tag_group_table = """\
CREATE TABLE IF NOT EXISTS tag_groups
(chat_id INTEGER, group_name TEXT, emojis TEXT, tags JSON, PRIMARY KEY (chat_id, group_name))"""
        word_counter_table = """\
CREATE TABLE IF NOT EXISTS word_counter
(chat_id INTEGER, word TEXT, count INTEGER DEFAULT 0, PRIMARY KEY (chat_id, word))"""
        student_info_table = """\
CREATE TABLE IF NOT EXISTS student_info
(chat_id INTEGER, student_id INTEGER, name TEXT, surname TEXT, email TEXT, PRIMARY KEY (chat_id, student_id))"""

        self.conn.execute(tag_group_table)
        self.conn.execute(word_counter_table)
        self.conn.execute(student_info_table)
        self.conn.commit()

    def __del__(self):
        self.conn.close()

    # student_info
    def insert_student_infos(self, chat_id: int, student_infos: list[StudentInfo]) -> int:
        to_insert = (
            (chat_id, student.student_id, student.name, student.surname, student.email) for student in student_infos
        )
        inserted_rows = self.conn.executemany(
            "INSERT OR IGNORE INTO student_info (chat_id, student_id, name, surname, email) VALUES (?, ?, ?, ?, ?)",
            to_insert,
        ).rowcount
        self.conn.commit()

        return inserted_rows

    def get_student_by_name(self, chat_id: int, name: str) -> list[StudentInfo]:
        student_infos = self.conn.execute(
            "SELECT student_id, name, surname, email FROM student_info WHERE chat_id = ? AND (name = ? OR surname = ?)",
            (chat_id, name, name),
        ).fetchall()
        return [StudentInfo(student_id, name, surname, email) for student_id, name, surname, email in student_infos]

    def get_student_by_id(self, chat_id: int, student_id: int) -> StudentInfo | None:
        student_info = self.conn.execute(
            "SELECT name, surname, email FROM student_info WHERE chat_id = ? AND student_id = ?",
            (chat_id, student_id),
        ).fetchone()
        if not student_info:
            return None

        return StudentInfo(student_id, name=student_info[0], surname=student_info[1], email=student_info[2])

    def delete_student_infos(self, chat_id: int) -> int:
        deleted = self.conn.execute("DELETE FROM student_info WHERE chat_id = ?", (chat_id,)).rowcount
        self.conn.commit()
        return deleted


def init_db(db_path: str) -> None:
    global _db  # noqa: PLW0603
    _db = DbHelper(db_path)


def with_db[**P, R](f: Callable[Concatenate[DbHelper, P], R]) -> Callable[P, R]:
    @functools.wraps(f)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return f(_db, *args, **kwargs)

    return inner
