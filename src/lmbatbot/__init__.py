import logging

from telegram import Update
from telegram.ext import Application

from lmbatbot import fun, tags  # , university_data, word_counter
from lmbatbot.database import engine
from lmbatbot.database.models import Base
from lmbatbot.settings import settings


async def set_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        (
            ("taglist", "Lists available tags"),
            ("tagadd", "Adds a tag group"),
            ("tagdel", "Deletes a tag group"),
            ("stats", "Shows group stats"),
            ("track", "Tracks a word"),
            ("untrack", "Stops tracking a word"),
            ("uni", "Shows student info about name / id"),
            ("uniset", "Adds new student data to this chat's DB"),
            ("unireset", "Deletes all records for the current chat"),
            ("bocchi", "Bocchi"),
            ("lt", "REEEEEEEEEEEEETI"),
        ),
    )


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    application = Application.builder().token(settings.TELEGRAM_TOKEN).post_init(set_commands).build()
    Base.metadata.create_all(engine)

    # . application.add_handlers(university_data.handlers())
    # . application.add_handlers(word_counter.handlers())
    application.add_handlers(tags.handlers())
    application.add_handlers(fun.handlers())

    application.run_polling(allowed_updates=Update.ALL_TYPES)
