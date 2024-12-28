import contextlib
import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from telegram import Message, MessageEntity, Update, constants
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from lmbatbot.database import Session
from lmbatbot.database.models import TagGroup
from lmbatbot.database.types import DeleteResult, UpsertResult
from lmbatbot.settings import settings
from lmbatbot.utils import CommandParsingError, TypedBaseHandler

logger = logging.getLogger(__name__)


@dataclass
class TagAddArgs:
    group: str
    tags: list[str]


def _parse_tagadd_command(effective_message: Message) -> TagAddArgs:
    """
    Command must contain the following arguments in any order.

    /tagadd <#group> <@mentions...>
    """
    hashtags = effective_message.parse_entities([MessageEntity.HASHTAG]).values()
    if len(hashtags) != 1:
        msg = f"Invalid number of tag groups, got: {list(hashtags)}"
        raise CommandParsingError(msg)

    text_mentions = effective_message.parse_entities([MessageEntity.TEXT_MENTION])
    if len(text_mentions) > 0:
        msg = f"TEXT_MENTION are not supported yet, these users cannot be added: {list(text_mentions.values())}"
        raise CommandParsingError(msg)

    mentions = effective_message.parse_entities([MessageEntity.MENTION]).values()
    if len(mentions) == 0:
        msg = "No mentions found"
        raise CommandParsingError(msg)

    return TagAddArgs(group=next(iter(hashtags)).lower(), tags=[mention.lower() for mention in mentions])


def _get_tag_groups(chat_id: int, groups: list[str] | None = None) -> list[TagGroup]:
    stmt = select(TagGroup).where(TagGroup.chat_id == chat_id)
    with Session() as session:
        if groups:
            tag_groups = session.scalars(stmt.where(TagGroup.group_name.in_(groups))).all()
        else:
            tag_groups = session.scalars(stmt).all()

    return list(tag_groups)


def _delete_tag_group(chat_id: int, group: str) -> DeleteResult:
    stmt = delete(TagGroup).where(TagGroup.chat_id == chat_id, TagGroup.group_name == group)
    with Session.begin() as session:
        deleted_rows = session.execute(stmt).rowcount

    if deleted_rows == 0:
        return DeleteResult.NOT_FOUND

    return DeleteResult.DELETED


def _upsert_tag_group(chat_id: int, tag_group: TagAddArgs) -> UpsertResult:
    insert_stmt = insert(TagGroup).values(
        {
            TagGroup.chat_id: chat_id,
            TagGroup.group_name: tag_group.group,
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


async def handle_message_with_tags(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    tags = list(update.effective_message.parse_entities([MessageEntity.HASHTAG]).values())

    found_groups = _get_tag_groups(update.effective_chat.id, tags)
    if len(found_groups) == 0:
        return

    tag_set: set[str] = set()
    for group in found_groups:
        tag_set = tag_set.union(group.tags)

    if username := update.effective_user.username:
        with contextlib.suppress(KeyError):
            tag_set.remove(f"@{username.lower()}")

    await update.effective_message.reply_html(" ".join(tag_set))

    # TODO: temporary implementation, create a table ad-hoc
    # https://github.com/ardubev16/lmbatbot/issues/12
    message = f"You got mentioned in <b>{update.effective_chat.effective_name}</b> by {update.effective_user.name}."
    for username, user_id in settings.GLOBAL_PVT_NOTIFICATION_USERS:
        if username.lower() in tag_set:
            logger.info("Sending private message to `%s`", user_id)
            await update.effective_message.reply_html(
                message,
                do_quote=update.effective_message.build_reply_arguments(target_chat_id=user_id),
            )


async def taglist_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat

    tag_groups = _get_tag_groups(update.effective_chat.id)

    string_group = [f"{group.group_name}: {", ".join(name.lstrip("@") for name in group.tags)}" for group in tag_groups]
    if len(string_group) != 0:
        message = f"""\
<b>Groups:</b>

{"\n\n".join(string_group)}"""
    else:
        message = """\
<i>There are no configured groups.</i>
Use the /tagadd to create a new group."""

    await update.effective_chat.send_message(message, parse_mode=constants.ParseMode.HTML)


async def tagadd_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    chat_id = update.effective_chat.id

    try:
        tag_group = _parse_tagadd_command(update.effective_message)
    except CommandParsingError as e:
        text = f"""\
{e}

Please use the following format:
/tagadd <#group> <@tags...>"""
        await update.effective_message.reply_text(text)
        return

    res = _upsert_tag_group(chat_id, tag_group)

    match res:
        case UpsertResult.UPDATED:
            text = f"Group {tag_group.group} updated!"
        case UpsertResult.INSERTED:
            text = f"Group {tag_group.group} added!"

    logger.info("User `%s` added new tag group `%s` in chat `%s`", update.effective_user.id, tag_group.group, chat_id)
    await update.effective_chat.send_message(text)


async def tagdel_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    chat_id = update.effective_chat.id

    hashtags = update.effective_message.parse_entities([MessageEntity.HASHTAG]).values()
    if len(hashtags) == 0:
        text = """\
Invalid format. Please use the following format:
/tagdel <#group...>"""
        await update.effective_message.reply_text(text)
        return

    texts: list[str] = []
    for group in hashtags:
        res = _delete_tag_group(chat_id, group)

        match res:
            case DeleteResult.DELETED:
                texts.append(f"Group {group} removed!")
            case DeleteResult.NOT_FOUND:
                texts.append(f"Group {group} not found!")

        logger.info("User `%s` deleted tag group `%s` in chat `%s`", update.effective_user.id, group, chat_id)

    await update.effective_chat.send_message("\n".join(texts))


def handlers() -> list[TypedBaseHandler]:
    taglist_handler = CommandHandler("taglist", taglist_cmd)
    tagadd_handler = CommandHandler("tagadd", tagadd_cmd)
    tagdel_handler = CommandHandler("tagdel", tagdel_cmd)
    tag_handler = MessageHandler(
        filters.Entity(constants.MessageEntityType.HASHTAG),
        handle_message_with_tags,
    )

    return [taglist_handler, tagadd_handler, tagdel_handler, tag_handler]
