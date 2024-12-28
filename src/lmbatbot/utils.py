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
        assert update.effective_chat
        await update.effective_chat.send_message(
            f"Bot version: <code>{version}</code>",
            parse_mode=constants.ParseMode.HTML,
            disable_notification=True,
        )

    return CommandHandler("version", _version_cmd)


type TypedBaseHandler = BaseHandler[Update, ContextTypes.DEFAULT_TYPE]
