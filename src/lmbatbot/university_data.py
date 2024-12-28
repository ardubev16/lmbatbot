import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from lmbatbot.database import Session
from lmbatbot.database.models import StudentInfo
from lmbatbot.utils import TypedBaseHandler, strip

logger = logging.getLogger(__name__)

FILE_UPLOAD_STATE = 1


@dataclass
class StudentInfoData:
    student_id: int
    name: str
    surname: str
    email: str


def _parse_file(file: bytearray) -> list[StudentInfoData]:
    raw_info = file.decode().splitlines()

    to_insert: list[StudentInfoData] = []
    for person in raw_info:
        try:
            email, student_id, name, surname, *_ = person.split(";")
            to_insert.append(
                StudentInfoData(
                    email=strip(email),
                    student_id=int(strip(student_id)),
                    name=strip(name),
                    surname=strip(surname),
                ),
            )
        except ValueError:
            return []
    return to_insert


def _handle_student_id(chat_id: int, student_id: int) -> str:
    with Session() as s:
        student = s.scalars(
            select(StudentInfo).where(StudentInfo.chat_id == chat_id, StudentInfo.student_id == student_id),
        ).one_or_none()

    if not student:
        return "No student found with such student_id!"

    return f"student_id <i>{student.student_id}</i> belongs to <b>{student.fullname}</b>"


def _handle_name(chat_id: int, name: str) -> str:
    with Session() as s:
        students = s.scalars(
            select(StudentInfo).where(
                StudentInfo.chat_id == chat_id,
                (StudentInfo.name == name) | (StudentInfo.surname == name),
            ),
        ).all()

    if not students:
        return "No student found with such name or surname!"

    return "\n".join(
        f"Student <i>{student.fullname}</i> has student_id <b>{student.student_id}</b>" for student in students
    )


async def uni_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_message

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("WARNING: You need to specify a name!")
        return
    name = context.args[0]

    if name.isnumeric():
        text = _handle_student_id(update.effective_chat.id, int(name))
    else:
        text = _handle_name(update.effective_chat.id, name)

    await update.effective_chat.send_message(text, protect_content=True, parse_mode=constants.ParseMode.HTML)


async def unireset_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    assert update.effective_user

    with Session.begin() as s:
        deleted = s.execute(delete(StudentInfo).where(StudentInfo.chat_id == update.effective_chat.id)).rowcount

    logger.info("User `%s` deleted student data for chat `%s`", update.effective_user.id, update.effective_chat.id)
    await update.effective_chat.send_message(f"{deleted} records have been deleted!")


async def uniset_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.effective_chat

    await update.effective_chat.send_message(
        """\
Send me a text file containing the data in newline separated strings with the following format:

<code>email;student_id;name;surname</code>

If you want to cancel the operation, send /cancel""",
        parse_mode=constants.ParseMode.HTML,
    )
    return FILE_UPLOAD_STATE


async def file_upload(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.effective_chat
    assert update.effective_message
    assert update.effective_message.document
    assert update.effective_user

    chat_id = update.effective_chat.id

    file_obj = await update.effective_message.document.get_file()
    file = await file_obj.download_as_bytearray()
    await update.effective_message.delete()

    to_insert = _parse_file(file)
    if not to_insert:
        logger.info("User `%s` sent a file with invalid format in chat `%s`", update.effective_user.id, chat_id)
        await update.effective_chat.send_message("WARNING: The file you sent is not valid!", disable_notification=True)
        return FILE_UPLOAD_STATE

    with Session.begin() as s:
        insert_stmt = insert(StudentInfo)
        s.execute(
            insert_stmt.on_conflict_do_nothing(),
            [
                {
                    "chat_id": chat_id,
                    "student_id": student.student_id,
                    "name": student.name,
                    "surname": student.surname,
                    "email": student.email,
                }
                for student in to_insert
            ],
        )
        total_chat_entries = s.scalars(
            select(func.count()).where(StudentInfo.chat_id == chat_id),
        ).one()

    logger.info(
        "User `%s` updated student data for chat `%s`, `%s` entries available",
        update.effective_user.id,
        chat_id,
        total_chat_entries,
    )
    await update.effective_chat.send_message(
        f"Successfully updated student data, <b>{total_chat_entries}</b> entries are now available in this chat!",
        disable_notification=True,
        parse_mode=constants.ParseMode.HTML,
    )

    return ConversationHandler.END


async def cancel_upload(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.effective_chat

    await update.effective_chat.send_message("Operation cancelled!", disable_notification=True)
    return ConversationHandler.END


async def file_upload_error(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.effective_chat

    await update.effective_chat.send_message(
        """\
WARNING: Invalid document format or message!
if you want to cancel the operation, send /cancel""",
        disable_notification=True,
    )
    return FILE_UPLOAD_STATE


def handlers() -> list[TypedBaseHandler]:
    uni_handler = CommandHandler("uni", uni_cmd)
    unireset_handler = CommandHandler("unireset", unireset_cmd)
    uniset_handler = ConversationHandler(
        entry_points=[CommandHandler("uniset", uniset_cmd)],
        states={
            FILE_UPLOAD_STATE: [
                MessageHandler(filters.Document.TEXT, file_upload),
                MessageHandler(
                    ~filters.Document.TEXT & ~filters.Regex("^/cancel"),
                    file_upload_error,
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_upload)],
    )

    return [uni_handler, unireset_handler, uniset_handler]
