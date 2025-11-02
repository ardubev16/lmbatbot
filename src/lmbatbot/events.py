import datetime
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes, JobQueue

from lmbatbot.settings import settings

logger = logging.getLogger(__name__)

def load_events() -> dict[tuple[int, int], tuple[str, datetime.time]]:
    """Loads events from the JSON file."""
    events_file = Path("data/static/events.json")
    if not events_file.exists():
        logger.warning("Events file not found: %s", events_file)
        return {}

    try:
        with events_file.open("r") as f:
            events_data = json.load(f)
    except json.JSONDecodeError:
        logger.exception("Error decoding events JSON file: %s", events_file)
        return {}

    events: dict[tuple[int, int], tuple[str, datetime.time]] = {}
    for i, event in enumerate(events_data):
        try:
            day = event["day"]
            month = event["month"]
            message = event["message"]
            time_str = event["time"]
            time = datetime.time.fromisoformat(time_str)
            events[(day, month)] = (message, time)
        except (KeyError, ValueError) as e:
            logger.error(
                "Skipping invalid event entry #%d in %s: %s",
                i,
                events_file,
                e,
            )
    return events

EVENT_MESSAGES = load_events()


async def send_event_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the event message."""
    if not (isinstance(context.job.data, dict) and (message := context.job.data.get("message"))):
        return
    await context.bot.send_message(chat_id=settings.EVENT_CHAT_ID, text=message)


async def event_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks if today there is an event and schedules a message if it is."""
    if not settings.EVENT_CHAT_ID:
        logger.info("EVENT_CHAT_ID not set, skipping event check.")
        return

    today = datetime.date.today()
    today_tuple = (today.day, today.month)

    if event := EVENT_MESSAGES.get(today_tuple):
        message, time = event
        event_time = time.replace(tzinfo=ZoneInfo("Europe/Rome"))
        logger.info("Today there is an event! Scheduling message for %s", event_time)
        if context.job_queue:
            context.job_queue.run_once(
                callback=send_event_message,
                when=event_time,
                data={"message": message},
                name=f"event_{today.day}_{today.month}",
            )


def schedule_event_check(job_queue: JobQueue) -> None:
    """Schedules the daily event check."""

    job_queue.run_once(
        event_check_job,
        when=0,
        name="event_check_job_immediate")
    logger.info("Scheduled immediate event check job.")

    daily_time = datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("Europe/Rome"))
    job_queue.run_daily(
        event_check_job,
        time=daily_time,
        name="event_check_job_daily")
    logger.info("Scheduled daily event check job.")
