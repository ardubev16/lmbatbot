from __future__ import annotations

import functools
import json
import sqlite3
from enum import Enum, auto
from typing import TYPE_CHECKING, Concatenate

from lmbatbot.models import StudentInfo, TagGroup, WordCount

if TYPE_CHECKING:
    from collections.abc import Callable


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

    # tag_groups
    def upsert_tag_group(self, chat_id: int, tag_group: TagGroup) -> UpsertResult:
        (group_exists,) = self.conn.execute(
            "SELECT COUNT(*) FROM tag_groups WHERE chat_id = ? AND group_name = ?",
            (chat_id, tag_group.group),
        ).fetchone()

        if group_exists:
            self.conn.execute(
                "UPDATE tag_groups SET emojis = ?, tags = ? WHERE chat_id = ? AND group_name = ?",
                (tag_group.emojis, json.dumps(tag_group.tags), chat_id, tag_group.group),
            )
            operation_done = UpsertResult.UPDATED
        else:
            self.conn.execute(
                "INSERT INTO tag_groups (chat_id, group_name, emojis, tags) VALUES (?, ?, ?, ?)",
                (chat_id, tag_group.group, tag_group.emojis, json.dumps(tag_group.tags)),
            )
            operation_done = UpsertResult.INSERTED

        self.conn.commit()
        return operation_done

    def get_tag_groups(self, chat_id: int, groups: list[str] | None = None) -> list[TagGroup]:
        tag_groups: list[tuple[str, str, str]]
        if not groups:
            tag_groups = self.conn.execute(
                "SELECT group_name, emojis, tags FROM tag_groups WHERE chat_id = ?",
                (chat_id,),
            ).fetchall()
        else:
            tag_groups = []
            for group in groups:
                tag_groups.append(
                    self.conn.execute(
                        "SELECT group_name, emojis, tags FROM tag_groups WHERE chat_id = ? AND group_name = ?",
                        (chat_id, group),
                    ).fetchone(),
                )

        return [
            TagGroup(group=tag_group[0], emojis=tag_group[1], tags=json.loads(tag_group[2])) for tag_group in tag_groups
        ]

    def delete_tag_group(self, chat_id: int, group: str) -> DeleteResult:
        deleted_rows = self.conn.execute(
            "DELETE FROM tag_groups WHERE chat_id = ? AND group_name = ?",
            (chat_id, group),
        ).rowcount
        self.conn.commit()

        if deleted_rows == 0:
            return DeleteResult.NOT_FOUND

        return DeleteResult.DELETED

    # word_counter
    def insert_word_to_track(self, chat_id: int, word: str) -> UpsertResult:
        try:
            self.conn.execute("INSERT INTO word_counter (chat_id, word) VALUES (?, ?)", (chat_id, word))
        except sqlite3.IntegrityError:  # UNIQUE constraint failed: word_counter.chat_id, word_counter.word
            self.conn.execute("UPDATE word_counter SET count = 0 WHERE chat_id = ? AND word = ?", (chat_id, word))
            return UpsertResult.UPDATED
        else:
            return UpsertResult.INSERTED
        finally:
            self.conn.commit()

    def get_tracked_words(self, chat_id: int) -> list[WordCount]:
        word_counts = self.conn.execute(
            "SELECT word, count FROM word_counter WHERE chat_id = ?",
            (chat_id,),
        ).fetchall()
        return [WordCount(word=word_count[0], count=word_count[1]) for word_count in word_counts]

    def add_to_word_count(self, chat_id: int, word: str, count: int) -> None:
        self.conn.execute(
            "UPDATE word_counter SET count = count + ? WHERE chat_id = ? AND word = ?",
            (count, chat_id, word),
        )
        self.conn.commit()

    def delete_tracked_word(self, chat_id: int, word: str) -> DeleteResult:
        deleted_rows = self.conn.execute(
            "DELETE FROM word_counter WHERE chat_id = ? AND word = ?",
            (chat_id, word),
        ).rowcount
        self.conn.commit()

        if deleted_rows == 0:
            return DeleteResult.NOT_FOUND

        return DeleteResult.DELETED

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


def init_db(db_path: str) -> None:
    global _db
    _db = DbHelper(db_path)


def with_db[**P, R](f: Callable[Concatenate[DbHelper, P], R]) -> Callable[P, R]:
    @functools.wraps(f)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return f(_db, *args, **kwargs)

    return inner
