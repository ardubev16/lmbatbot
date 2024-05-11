from telegram import Update, constants
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from lmbatbot.database import DbHelper, with_db
from lmbatbot.models import StudentInfo
from lmbatbot.utils import TypedBaseHandler, strip

FILE_UPLOAD_STATE = 1


def _parse_file(file: bytearray) -> list[StudentInfo]:
    raw_info = file.decode().splitlines()

    to_insert: list[StudentInfo] = []
    for person in raw_info:
        try:
            email, student_id, name, surname, *_ = person.split(";")
            to_insert.append(
                StudentInfo(
                    email=strip(email),
                    student_id=int(strip(student_id)),
                    name=strip(name),
                    surname=strip(surname),
                ),
            )
        except ValueError:
            return []
    return to_insert


def _handle_student_id(db_helper: DbHelper, chat_id: int, student_id: int) -> str:
    student = db_helper.get_student_by_id(chat_id, student_id)
    if not student:
        return "No student found with such student_id!"

    return f"student_id <i>{student.student_id}</i> belongs to <b>{student.fullname}</b>"


def _handle_name(db_helper: DbHelper, chat_id: int, name: str) -> str:
    students = db_helper.get_student_by_name(chat_id, name)
    if not students:
        return "No student found with such name or surname!"

    return "\n".join(
        f"Student <i>{student.fullname}</i> has student_id <b>{student.student_id}</b>" for student in students
    )


@with_db
async def uni_cmd(db_helper: DbHelper, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("WARNING: You need to specify a name!")
        return
    name = context.args[0]

    if name.isnumeric():
        text = _handle_student_id(db_helper, update.effective_chat.id, int(name))
    else:
        text = _handle_name(db_helper, update.effective_chat.id, name)

    await update.effective_chat.send_message(text, protect_content=True, parse_mode=constants.ParseMode.HTML)


async def uniset_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message(
        """\
Send me a text file containing the data in newline separated strings with the following format:

<code>email;student_id;name;surname</code>

If you want to cancel the operation, send /cancel""",
        parse_mode=constants.ParseMode.HTML,
    )
    return FILE_UPLOAD_STATE


@with_db
async def file_upload(db_helper: DbHelper, update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    file_obj = await update.effective_message.document.get_file()
    file = await file_obj.download_as_bytearray()
    await update.effective_message.delete()

    to_insert = _parse_file(file)
    if not to_insert:
        await update.effective_chat.send_message("WARNING: The file you sent is not valid!", disable_notification=True)
        return FILE_UPLOAD_STATE

    inserted_entries = db_helper.insert_student_infos(update.effective_chat.id, to_insert)

    await update.effective_chat.send_message(
        f"Successfully added {inserted_entries} students' data to the database!",
        disable_notification=True,
    )

    return ConversationHandler.END


async def cancel_upload(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message("Operation cancelled!", disable_notification=True)
    return ConversationHandler.END


async def file_upload_error(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message(
        """\
WARNING: Invalid document format or message!
if you want to cancel the operation, send /cancel""",
        disable_notification=True,
    )
    return FILE_UPLOAD_STATE


def handlers() -> list[TypedBaseHandler]:
    uni_handler = CommandHandler("uni", uni_cmd)
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

    return [uni_handler, uniset_handler]
