import logging

from telegram import Update
from telegram.ext import Application

from lmbatbot import fun, tags, university_data, word_counter
from lmbatbot.settings import settings
from lmbatbot.utils import version_command_handler


async def _set_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        (
            *university_data.commands,
            *word_counter.commands,
            *tags.commands,
            ("bocchi", "Bocchi"),
            ("lt", "REEEEEEEEEEEEETI"),
            ("version", "Display bot version"),
        ),
    )


def main() -> None:
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    application = Application.builder().token(settings.TELEGRAM_TOKEN).post_init(_set_commands).build()

    application.add_handlers(university_data.handlers())
    application.add_handlers(word_counter.handlers())
    application.add_handlers(tags.handlers())
    application.add_handlers(fun.handlers())
    application.add_handler(version_command_handler())

    application.run_polling(allowed_updates=Update.ALL_TYPES)
