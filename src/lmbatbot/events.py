import datetime
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays
from telegram.ext import ContextTypes, JobQueue

from lmbatbot.settings import settings

logger = logging.getLogger(__name__)

it_holidays = holidays.IT()

def load_events() -> (
    tuple[
        dict[tuple[int, int], list[tuple[str, datetime.time]]],
        dict[str, list[tuple[str, datetime.time]]],
    ]
):
    """Loads events from the JSON file."""
    events_file = Path("data/static/events.json")
    if not events_file.exists():
        logger.warning("Events file not found: %s", events_file)
        return {}, {}

    try:
        with events_file.open("r") as f:
            events_data = json.load(f)
    except json.JSONDecodeError:
        logger.exception("Error decoding events JSON file: %s", events_file)
        return {}, {}

    date_events: dict[tuple[int, int], list[tuple[str, datetime.time]]] = {}
    name_events: dict[str, list[tuple[str, datetime.time]]] = {}
    for i, event in enumerate(events_data):
        try:
            message = event["message"]
            time_str = event["time"]
            time = datetime.time.fromisoformat(time_str)

            if name := event.get("name"):
                name_events.setdefault(name, []).append((message, time))

            if day := event.get("day"):
                if month := event.get("month"):
                    date_events.setdefault((day, month), []).append((message, time))

        except (KeyError, ValueError) as e:
            logger.error(
                "Skipping invalid event entry #%d in %s: %s",
                i,
                events_file,
                e,
            )
    return date_events, name_events


DATE_EVENTS, NAME_EVENTS = load_events()


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

    events_to_schedule = []

    holiday_name = it_holidays.get(today)
    if holiday_name:
        if events_by_name := NAME_EVENTS.get(holiday_name):
            events_to_schedule.extend(events_by_name)
            logger.info("Found %d holiday event(s) for %s", len(events_by_name), holiday_name)

    today_tuple = (today.day, today.month)
    if events_by_date := DATE_EVENTS.get(today_tuple):
        new_events = [event for event in events_by_date if event not in events_to_schedule]
        if new_events:
            events_to_schedule.extend(new_events)
            logger.info(
                "Found %d new fixed-date event(s) for %d/%d",
                len(new_events),
                today.day,
                today.month,
            )

    if not events_to_schedule:
        return

    logger.info("Found %d event(s) for today. Scheduling now.", len(events_to_schedule))
    if context.job_queue:
        for i, (message, time) in enumerate(events_to_schedule):
            event_time = time.replace(tzinfo=ZoneInfo("Europe/Rome"))
            job_name = f"event_{today.day}_{today.month}_{i}"
            context.job_queue.run_once(
                callback=send_event_message,
                when=event_time,
                data={"message": message},
                name=job_name,
            )
            logger.info("Scheduled job '%s' for %s", job_name, event_time)


def schedule_event_check(job_queue: JobQueue) -> None:
    """Schedules the daily event check."""

    job_queue.run_once(event_check_job, when=0, name="event_check_job_immediate")
    logger.info("Scheduled immediate event check job.")

    daily_time = datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("Europe/Rome"))
    job_queue.run_daily(event_check_job, time=daily_time, name="event_check_job_daily")
    logger.info("Scheduled daily event check job.")
