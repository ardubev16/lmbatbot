import json
import random
from pathlib import Path

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from lmbatbot.utils import TypedBaseHandler

STATIC_PATH = Path("./data/static/")


def get_sticker_ids() -> dict[str, list[str]]:
    stickers_file = STATIC_PATH / "stickers.json"
    with stickers_file.open() as content:
        return json.load(content)


async def stickers(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_message.text

    full_command = update.effective_message.text.split()[0]
    command = full_command.split("@")[0].lstrip("/")

    sticker_list = get_sticker_ids()[command]
    rn = random.randint(0, len(sticker_list) - 1)
    await update.effective_chat.send_sticker(sticker_list[rn])


async def lt(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat

    lt_content_file = STATIC_PATH / "lt_content.txt"
    with lt_content_file.open() as file:
        await update.effective_chat.send_message(file.read())


def handlers() -> list[TypedBaseHandler]:
    handlers: list[TypedBaseHandler] = [CommandHandler(key, stickers) for key in get_sticker_ids()]
    handlers.append(CommandHandler("lt", lt))

    return handlers
