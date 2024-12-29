from telegram import Update, constants
from telegram.ext import BaseHandler, CommandHandler, ContextTypes


def strip(text: str) -> str:
    return text.lower().strip('"').strip("'").strip()


class CommandParsingError(Exception):
    """Error during command parsing."""


class NotEnoughArgsError(CommandParsingError):
    def __init__(self, argc: int):
        super().__init__(f"Not enough args, got {argc}")


def version_command() -> CommandHandler:
    async def _version_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        import importlib.metadata

        version = importlib.metadata.version("lmbatbot")
        release_notes_url = f"https://github.com/ardubev16/lmbatbot/releases/tag/v{version}"
        message = f"""\
Bot version: <code>{version}</code>

To see what's changed checkout the <a href='{release_notes_url}'>Release Notes</a>"""
        assert update.effective_chat
        await update.effective_chat.send_message(
            message,
            parse_mode=constants.ParseMode.HTML,
            disable_notification=True,
        )

    return CommandHandler("version", _version_cmd)


type TypedBaseHandler = BaseHandler[Update, ContextTypes.DEFAULT_TYPE]
