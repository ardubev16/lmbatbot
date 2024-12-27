import re

from sqlalchemy import delete, select
from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from lmbatbot.database import Session
from lmbatbot.database.models import WordCounter
from lmbatbot.database.types import DeleteResult, UpsertResult
from lmbatbot.utils import TypedBaseHandler


def insert_word_to_track(chat_id: int, word: str) -> UpsertResult:
    with Session.begin() as s:
        word_counter = s.scalars(
            select(WordCounter).where(WordCounter.chat_id == chat_id, WordCounter.word == word),
        ).one_or_none()

        if word_counter:
            word_counter.count = 0
            return UpsertResult.UPDATED

        s.add(WordCounter(chat_id=chat_id, word=word))
        return UpsertResult.INSERTED


def delete_tracked_word(chat_id: int, word: str) -> DeleteResult:
    with Session.begin() as s:
        deleted_rows = s.execute(
            delete(WordCounter).where(WordCounter.chat_id == chat_id, WordCounter.word == word),
        ).rowcount

    if deleted_rows == 0:
        return DeleteResult.NOT_FOUND

    return DeleteResult.DELETED


async def count_words_in_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_message.text

    with Session.begin() as s:
        tracked_words = s.scalars(select(WordCounter).where(WordCounter.chat_id == update.effective_chat.id)).all()

        for word_counter in tracked_words:
            cnt = len(re.findall(word_counter.word, update.effective_message.text, re.IGNORECASE))
            word_counter.count += cnt


async def stats_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat

    with Session() as s:
        word_counts = s.scalars(select(WordCounter).where(WordCounter.chat_id == update.effective_chat.id)).all()

    if len(word_counts) != 0:
        word_counts = sorted(word_counts, key=lambda x: x.count, reverse=True)
        stats = [f"{word_count.word.capitalize()}: {word_count.count}" for word_count in word_counts]
        text = f"""\
<b>Stats</b>

{"\n".join(stats)}"""
    else:
        text = """\
<i>There are no tracked words.</i>
Use the /track to start tracking a new word."""

    await update.effective_chat.send_message(text, parse_mode=constants.ParseMode.HTML)


async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Please specify a word to add!", disable_notification=True)
        return
    word = context.args[0].lower()

    res = insert_word_to_track(update.effective_chat.id, word)
    match res:
        case UpsertResult.UPDATED:
            text = f"WARNING: <b>{word.capitalize()}</b> counter has been reset!"
        case UpsertResult.INSERTED:
            text = f"Added <b>{word.capitalize()}</b> to the list!"

    await update.effective_chat.send_message(text, disable_notification=True, parse_mode=constants.ParseMode.HTML)


async def untrack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Please specify a word to add!", disable_notification=True)
        return
    word = context.args[0].lower()

    res = delete_tracked_word(update.effective_chat.id, word)
    match res:
        case DeleteResult.DELETED:
            text = f"Removed <b>{word.capitalize()}</b> from the list!"
        case DeleteResult.NOT_FOUND:
            text = f"WARNING: <b>{word.capitalize()}</b> was not on the list!"

    await update.effective_chat.send_message(text, disable_notification=True, parse_mode=constants.ParseMode.HTML)


def handlers() -> dict[int, list[TypedBaseHandler] | tuple[TypedBaseHandler]]:
    DEFAULT, TRACKER = range(2)  # noqa: N806

    stats_handler = CommandHandler("stats", stats_cmd)
    track_handler = CommandHandler("track", track_cmd)
    untrack_handler = CommandHandler("untrack", untrack_cmd)
    message_handler = MessageHandler(
        filters.TEXT,
        count_words_in_message,
    )

    return {
        DEFAULT: [stats_handler, track_handler, untrack_handler],
        TRACKER: [message_handler],
    }
