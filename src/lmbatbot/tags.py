import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from lmbatbot.database import Session
from lmbatbot.database.models import TagGroup
from lmbatbot.database.types import DeleteResult, UpsertResult
from lmbatbot.settings import settings
from lmbatbot.utils import CommandParsingError, NotEnoughArgsError, TypedBaseHandler

logger = logging.getLogger(__name__)


@dataclass
class TagAddArgs:
    group: str
    emojis: str
    tags: list[str]


def get_tag_groups(chat_id: int, groups: list[str] | None = None) -> list[TagGroup]:
    stmt = select(TagGroup).where(TagGroup.chat_id == chat_id)
    with Session() as session:
        if groups:
            tag_groups = session.scalars(stmt.where(TagGroup.group_name.in_(groups))).all()
        else:
            tag_groups = session.scalars(stmt).all()

    return list(tag_groups)


async def handle_message_with_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    tags = list(update.effective_message.parse_entities([constants.MessageEntityType.HASHTAG]).values())

    found_groups = get_tag_groups(update.effective_chat.id, tags)
    if len(found_groups) == 0:
        return

    emojis = ""
    tag_set: set[str] = set()
    for group in found_groups:
        emojis += group.emojis
        tag_set = tag_set.union(group.tags)

    tag_list = [tag for tag in tag_set if tag.lstrip("@") != update.effective_user.username]
    content = update.effective_message.text_html_urled

    message = f"""\
<i>{emojis} {update.effective_user.name}</i>
{content}

<i>{" ".join(tag_list)}</i>"""

    await update.effective_message.delete()
    await update.effective_chat.send_message(message, parse_mode=constants.ParseMode.HTML)

    # TODO: temporary implementation, create a table ad-hoc
    # https://github.com/ardubev16/lmbatbot/issues/12
    for username, user_id in settings.GLOBAL_PVT_NOTIFICATION_USERS:
        if username in tag_list:
            logger.info("Sending private message to `%s`", user_id)
            await context.bot.send_message(user_id, message, parse_mode=constants.ParseMode.HTML)


async def taglist_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat

    tag_groups = get_tag_groups(update.effective_chat.id)

    string_group = [
        f"{group.emojis} {group.group_name}: {", ".join(name.lstrip("@") for name in group.tags)}"
        for group in tag_groups
    ]
    if len(string_group) != 0:
        message = f"""\
<b>Groups:</b>

{"\n\n".join(string_group)}"""
    else:
        message = """\
<i>There are no configured groups.</i>
Use the /tagadd to create a new group."""

    await update.effective_chat.send_message(message, parse_mode=constants.ParseMode.HTML)


def _parse_tagadd_command(args: list[str] | None) -> TagAddArgs:
    """
    Command must respect the following format.

    /tagadd <emoji> <#group> <@tags...>
    """
    if not args or len(args) < 3:  # noqa: PLR2004
        raise NotEnoughArgsError(len(args or []))

    emojis, group_name, *tags = (arg.lower() for arg in args)
    if not group_name.startswith("#"):
        msg = "Invalid group name"
        raise CommandParsingError(msg)
    if not all(tag.startswith("@") for tag in tags):
        msg = "Invalid tags"
        raise CommandParsingError(msg)

    return TagAddArgs(group=group_name, emojis=emojis, tags=tags)


def upsert_tag_group(chat_id: int, tag_group: TagAddArgs) -> UpsertResult:
    insert_stmt = insert(TagGroup).values(
        {
            TagGroup.chat_id: chat_id,
            TagGroup.group_name: tag_group.group,
            TagGroup.emojis: tag_group.emojis,
            TagGroup.tags: tag_group.tags,
        },
    )
    insert_stmt = insert_stmt.on_conflict_do_update(set_=dict(insert_stmt.excluded))
    with Session.begin() as session:
        row_exists = session.execute(
            select(func.count())
            .select_from(TagGroup)
            .where(TagGroup.chat_id == chat_id, TagGroup.group_name == tag_group.group),
        ).scalar_one_or_none()

        session.execute(insert_stmt)

    return UpsertResult.UPDATED if row_exists else UpsertResult.INSERTED


async def tagadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    chat_id = update.effective_chat.id

    try:
        tag_group = _parse_tagadd_command(context.args)
    except CommandParsingError as e:
        text = f"""\
{e}

Please use the following format:
/tagadd <emoji> <#group> <@tags>"""
        await update.effective_message.reply_text(text)
        return

    res = upsert_tag_group(chat_id, tag_group)

    match res:
        case UpsertResult.UPDATED:
            text = f"Group {tag_group.group} updated!"
        case UpsertResult.INSERTED:
            text = f"Group {tag_group.group} added!"

    logger.info("User `%s` added new tag group `%s` in chat `%s`", update.effective_user.id, tag_group.group, chat_id)
    await update.effective_chat.send_message(text)


def delete_tag_group(chat_id: int, group: str) -> DeleteResult:
    stmt = delete(TagGroup).where(TagGroup.chat_id == chat_id, TagGroup.group_name == group)
    with Session.begin() as session:
        deleted_rows = session.execute(stmt).rowcount

    if deleted_rows == 0:
        return DeleteResult.NOT_FOUND

    return DeleteResult.DELETED


async def tagdel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    chat_id = update.effective_chat.id

    if not context.args or len(context.args) != 1 or not context.args[0].startswith("#"):
        text = """\
Invalid format. Please use the following format:
/tagdel <group>"""
        await update.effective_message.reply_text(text)
        return

    group = context.args[0]

    res = delete_tag_group(chat_id, group)

    match res:
        case DeleteResult.DELETED:
            text = f"Group {group} removed!"
        case DeleteResult.NOT_FOUND:
            text = f"Group {group} not found!"

    logger.info("User `%s` deleted tag group `%s` in chat `%s`", update.effective_user.id, group, chat_id)
    await update.effective_chat.send_message(text)


def handlers() -> list[TypedBaseHandler]:
    taglist_handler = CommandHandler("taglist", taglist_cmd)
    tagadd_handler = CommandHandler("tagadd", tagadd_cmd)
    tagdel_handler = CommandHandler("tagdel", tagdel_cmd)
    tag_handler = MessageHandler(
        filters.Entity(constants.MessageEntityType.HASHTAG),
        handle_message_with_tags,
    )

    return [taglist_handler, tagadd_handler, tagdel_handler, tag_handler]
