import re

from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from lmbatbot.database import DbHelper, DeleteResult, UpsertResult, with_db
from lmbatbot.utils import TypedBaseHandler


@with_db
async def count_words_in_message(db_helper: DbHelper, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_message.text

    tracked_words = db_helper.get_tracked_words(update.effective_chat.id)
    for word_count in tracked_words:
        cnt = len(re.findall(word_count.word, update.effective_message.text, re.IGNORECASE))
        db_helper.add_to_word_count(update.effective_chat.id, word_count.word, cnt)


@with_db
async def stats_cmd(db_helper: DbHelper, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat

    word_counts = db_helper.get_tracked_words(update.effective_chat.id)
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


@with_db
async def track_cmd(db_helper: DbHelper, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Please specify a word to add!", disable_notification=True)
        return
    word = context.args[0].lower()

    res = db_helper.insert_word_to_track(update.effective_chat.id, word)
    match res:
        case UpsertResult.UPDATED:
            text = f"WARNING: <b>{word.capitalize()}</b> counter has been reset!"
        case UpsertResult.INSERTED:
            text = f"Added <b>{word.capitalize()}</b> to the list!"

    await update.effective_chat.send_message(text, disable_notification=True, parse_mode=constants.ParseMode.HTML)


@with_db
async def untrack_cmd(db_helper: DbHelper, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Please specify a word to add!", disable_notification=True)
        return
    word = context.args[0].lower()

    res = db_helper.delete_tracked_word(update.effective_chat.id, word)
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
