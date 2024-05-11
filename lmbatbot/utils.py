from telegram import Update
from telegram.ext import BaseHandler, ContextTypes


def strip(text: str) -> str:
    return text.lower().strip('"').strip("'").strip()


class CommandParsingError(Exception):
    """Error during command parsing."""


class NotEnoughArgsError(CommandParsingError):
    def __init__(self, argc: int):
        super().__init__(f"Not enough args, got {argc}")


type TypedBaseHandler = BaseHandler[Update, ContextTypes.DEFAULT_TYPE]
