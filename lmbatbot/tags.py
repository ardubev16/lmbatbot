from pydantic.fields import Field
from pydantic_settings import BaseSettings
from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from lmbatbot.database import DbHelper, DeleteResult, UpsertResult, with_db
from lmbatbot.models import TagGroup
from lmbatbot.utils import CommandParsingError, NotEnoughArgsError, TypedBaseHandler


class TagsSettings(BaseSettings):
    GLOBAL_PVT_NOTIFICATION_USERS: list[tuple[str, int]] = Field(default=[])


async def handle_message_mentions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_message
    assert update.effective_user
    assert update.effective_chat

    mentioned_usernames = set(update.effective_message.parse_entities([constants.MessageEntityType.MENTION]).values())

    # Verifica se ci sono menzioni nel messaggio
    if not mentioned_usernames:
        return

    group_name = update.effective_chat.title or "gruppo"

    # Ottieni il link al messaggio originale
    try:
        group_message_link = f"https://t.me/c/{str(update.effective_chat.id)[4:]}/{update.effective_message.message_id}"
    except Exception as e:
        print(f"Errore nella generazione del link al messaggio: {e}")
        group_message_link = None

    for username in mentioned_usernames:
        # Rimuovi "@" dal nome utente menzionato
        clean_username = username.lstrip("@")

        # Trova l'ID dell'utente menzionato dai tuoi dati di configurazione
        user_id = next(
            (user_id for u, user_id in TagsSettings().GLOBAL_PVT_NOTIFICATION_USERS if u == clean_username),
            None,
        )

        if user_id:
            try:
                # Inoltra il messaggio in privato
                private_message = f"Hai ricevuto una menzione nel gruppo '{group_name}':\n\n"

                if group_message_link:
                    private_message += f"[Clicca qui per vedere il messaggio originale]({group_message_link})"
                await context.bot.send_message(chat_id=user_id, text=private_message, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception as e:
                print(f"Errore durante l'invio del messaggio a {username}: {e}")


@with_db
async def handle_message_with_tags(db_helper: DbHelper, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_user

    tags = list(update.effective_message.parse_entities([constants.MessageEntityType.HASHTAG]).values())

    found_groups = db_helper.get_tag_groups(update.effective_chat.id, tags)
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

    group_name = update.effective_chat.title or "gruppo"

    tag_list = [tag.lstrip('@') for tag in tag_list]

    # FIXME: temporary implementation, will be created a table ad-hoc
    settings = TagsSettings()
    for username, user_id in settings.GLOBAL_PVT_NOTIFICATION_USERS:
        if username.lower() in tag_list:
            try:
                # Crea il link al messaggio nel gruppo
                try:
                    group_message_link = f"https://t.me/c/{str(update.effective_chat.id)[4:]}/{update.effective_message.message_id}"
                except Exception as e:
                    print(f"Errore nella generazione del link al messaggio: {e}")
                    group_message_link = None

                # Prepara il messaggio da inviare in privato
                private_message = (
                    f"Hai ricevuto un messaggio dal gruppo '{group_name}':\n\n"
                )
                
                # Aggiungi il link al messaggio originale se disponibile
                if group_message_link:
                    private_message += f"[Clicca qui per vedere il messaggio originale]({group_message_link})"

                # Invia il messaggio privato
                await context.bot.send_message(user_id, private_message, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception as e:
                print(f"Errore durante l'invio del messaggio a {username}: {e}")




@with_db
async def taglist_cmd(db_helper: DbHelper, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat

    tag_groups = db_helper.get_tag_groups(update.effective_chat.id)

    string_group = [
        f"{group.emojis} {group.group}: {", ".join(name.lstrip("@") for name in group.tags)}" for group in tag_groups
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


def _parse_tagadd_command(args: list[str] | None) -> TagGroup:
    """
    Command must respect the following format.

    /tagadd <emoji> <#group> <@tags...>
    """
    if not args or len(args) < 3:  # noqa: PLR2004
        raise NotEnoughArgsError(len(args or []))

    emojis, group_name, *tags = (arg.lower() for arg in args)
    if not group_name.startswith("#"):
        raise CommandParsingError("Invalid group name")
    if not all(tag.startswith("@") for tag in tags):
        raise CommandParsingError("Invalid tags")

    return TagGroup(group=group_name, emojis=emojis, tags=tags)


@with_db
async def tagadd_cmd(db_helper: DbHelper, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    try:
        tag_group = _parse_tagadd_command(context.args)
    except CommandParsingError as e:
        text = f"""\
{e}

Please use the following format:
/tagadd <emoji> <#group> <@tags>"""
        await update.effective_message.reply_text(text)
        return

    res = db_helper.upsert_tag_group(update.effective_chat.id, tag_group)

    match res:
        case UpsertResult.UPDATED:
            text = f"Group {tag_group.group} updated!"
        case UpsertResult.INSERTED:
            text = f"Group {tag_group.group} added!"

    await update.effective_chat.send_message(text)


@with_db
async def tagdel_cmd(db_helper: DbHelper, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    if not context.args or len(context.args) != 1 or not context.args[0].startswith("#"):
        text = """\
Invalid format. Please use the following format:
/tagdel <group>"""
        await update.effective_message.reply_text(text)
        return

    group = context.args[0]

    res = db_helper.delete_tag_group(update.effective_chat.id, group)

    match res:
        case DeleteResult.DELETED:
            text = f"Group {group} removed!"
        case DeleteResult.NOT_FOUND:
            text = f"Group {group} not found!"

    await update.effective_chat.send_message(text)


def handlers() -> list[TypedBaseHandler]:
    taglist_handler = CommandHandler("taglist", taglist_cmd)
    tagadd_handler = CommandHandler("tagadd", tagadd_cmd)
    tagdel_handler = CommandHandler("tagdel", tagdel_cmd)
    tag_handler = MessageHandler(
        filters.Entity(constants.MessageEntityType.HASHTAG),
        handle_message_with_tags,
    )
    mention_handler = MessageHandler(
        filters.Entity(constants.MessageEntityType.MENTION),
        handle_message_mentions,
    )

    return [taglist_handler, tagadd_handler, tagdel_handler, tag_handler, mention_handler]
