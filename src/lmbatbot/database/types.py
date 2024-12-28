from enum import Enum, auto


class UpsertResult(Enum):
    INSERTED = auto()
    UPDATED = auto()


class DeleteResult(Enum):
    DELETED = auto()
    NOT_FOUND = auto()
