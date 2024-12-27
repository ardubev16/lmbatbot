from dataclasses import dataclass


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
