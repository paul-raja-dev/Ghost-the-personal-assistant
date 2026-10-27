"""TickTick Task Creation Tool for Ghost."""
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import config
import ticktick

PRIORITY = {"none": 0, "low": 1, "medium": 3, "high": 5}


def add_task(
    title: str,
    due: str = "",
    priority: str = "none",
    repeat: str = "",
    notes: str = "",
) -> dict:
    """Create a task or reminder in TickTick.

    Args:
        title: Short task title, e.g. "Call the vendor".
        due: Due date/time in the user's local timezone. Use "YYYY-MM-DDTHH:MM"
            (24h) when a time is given, "YYYY-MM-DD" when only a day is given,
            or empty string if no date was mentioned.
        priority: One of "none", "low", "medium", "high".
        repeat: iCalendar RRULE for repeating tasks, e.g. "RRULE:FREQ=DAILY;INTERVAL=1"
            or "RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO". Empty string if not repeating.
            A repeating task must also have a due date.
        notes: Optional extra detail for the task description.

    Returns:
        A dict with status "ok" or "error" and a message.
    """
    tz = ZoneInfo(config.TZ_NAME)
    payload: dict = {"title": title.strip(), "priority": PRIORITY.get(priority.lower(), 0)}
    if not payload["title"]:
        return {"status": "error", "message": "Title is empty."}
    if notes:
        payload["content"] = notes
    if config.TICKTICK_PROJECT_ID:
        payload["projectId"] = config.TICKTICK_PROJECT_ID

    if due:
        try:
            if "T" in due:
                dt = datetime.strptime(due, "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
                payload["isAllDay"] = False
                payload["reminders"] = ["TRIGGER:PT0S"]
            else:
                dt = datetime.strptime(due, "%Y-%m-%d").replace(tzinfo=tz)
                payload["isAllDay"] = True
                payload["reminders"] = ["TRIGGER:P0DT9H0M0S"]
        except ValueError:
            return {"status": "error", "message": f"Bad due format '{due}'. Use YYYY-MM-DDTHH:MM or YYYY-MM-DD."}
        stamp = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        payload["startDate"] = stamp
        payload["dueDate"] = stamp
        payload["timeZone"] = config.TZ_NAME

    if repeat:
        if not repeat.startswith("RRULE:"):
            return {"status": "error", "message": "repeat must start with 'RRULE:'."}
        if not due:
            return {"status": "error", "message": "A repeating task needs a due date."}
        payload["repeatFlag"] = repeat

    try:
        ticktick.create_task(payload)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "ok", "message": f"Created '{payload['title']}'", "due": due or "no date"}
