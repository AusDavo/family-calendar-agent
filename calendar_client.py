import os
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import caldav
from icalendar import Calendar as iCalCalendar

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Australia/Brisbane"))


@dataclass
class CalendarEvent:
    title: str
    start: datetime | date
    end: datetime | date
    all_day: bool
    location: str | None
    description: str | None
    calendar_name: str


class CalendarError(Exception):
    pass


def _get_client() -> caldav.DAVClient:
    return caldav.DAVClient(
        url=os.environ["CALDAV_URL"],
        username=os.environ["CALDAV_USERNAME"],
        password=os.environ["CALDAV_PASSWORD"],
    )


def _get_calendars(client: caldav.DAVClient) -> list[caldav.Calendar]:
    # Use calendar_home_set directly from the URL to avoid PROPFIND
    # principal discovery which fails with niquests + Fastmail redirects
    calendar_home = caldav.CalendarSet(client=client, url=os.environ["CALDAV_URL"])
    calendars = calendar_home.calendars()

    filter_names = os.environ.get("CALENDAR_NAMES", "").strip()
    if filter_names:
        allowed = {n.strip().lower() for n in filter_names.split(",") if n.strip()}
        calendars = [c for c in calendars if c.name.lower() in allowed]

    return calendars


def _parse_vevent(vevent, calendar_name: str) -> CalendarEvent:
    title = str(vevent.get("SUMMARY", "Untitled"))

    dtstart = vevent.get("DTSTART")
    start_val = dtstart.dt if dtstart else date.today()

    # Determine if all-day: DTSTART is a date but not a datetime
    all_day = isinstance(start_val, date) and not isinstance(start_val, datetime)

    # Get end time
    dtend = vevent.get("DTEND")
    duration = vevent.get("DURATION")

    if dtend:
        end_val = dtend.dt
    elif duration:
        end_val = start_val + duration.dt
    elif all_day:
        end_val = start_val + timedelta(days=1)
    else:
        end_val = start_val + timedelta(hours=1)

    # Normalize datetimes to local timezone
    if not all_day:
        if isinstance(start_val, datetime):
            if start_val.tzinfo is None:
                start_val = start_val.replace(tzinfo=TIMEZONE)
            else:
                start_val = start_val.astimezone(TIMEZONE)
        if isinstance(end_val, datetime):
            if end_val.tzinfo is None:
                end_val = end_val.replace(tzinfo=TIMEZONE)
            else:
                end_val = end_val.astimezone(TIMEZONE)

    location = str(vevent.get("LOCATION")) if vevent.get("LOCATION") else None
    description = str(vevent.get("DESCRIPTION")) if vevent.get("DESCRIPTION") else None

    return CalendarEvent(
        title=title,
        start=start_val,
        end=end_val,
        all_day=all_day,
        location=location,
        description=description,
        calendar_name=calendar_name,
    )


def get_events(start_date: str, end_date: str) -> list[CalendarEvent]:
    """Fetch events between start_date and end_date (inclusive).

    Args:
        start_date: ISO format date string "YYYY-MM-DD"
        end_date: ISO format date string "YYYY-MM-DD"

    Returns:
        List of CalendarEvent sorted by start time.
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
        # End of day for inclusive end date
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=TIMEZONE
        )

        client = _get_client()
        calendars = _get_calendars(client)
        events: list[CalendarEvent] = []

        for cal in calendars:
            results = cal.date_search(start=start, end=end, expand=True)
            for result in results:
                ical = iCalCalendar.from_ical(result.data)
                for component in ical.walk():
                    if component.name == "VEVENT":
                        events.append(_parse_vevent(component, cal.name))

        # Sort by start time (all-day events first, then by time)
        def sort_key(e: CalendarEvent):
            if isinstance(e.start, datetime):
                return (0, e.start)
            # All-day events: convert date to datetime for comparison
            return (0, datetime.combine(e.start, datetime.min.time(), tzinfo=TIMEZONE))

        events.sort(key=sort_key)
        return events

    except (caldav.error.AuthorizationError, caldav.error.DAVError) as e:
        raise CalendarError(f"Calendar connection failed: {e}") from e
    except Exception as e:
        raise CalendarError(f"Failed to fetch events: {e}") from e


def format_events_for_llm(events: list[CalendarEvent]) -> str:
    """Format events into a concise text block for the LLM prompt."""
    if not events:
        return ""

    lines = []
    current_date = None

    for event in events:
        event_date = event.start if event.all_day else event.start.date()
        if event_date != current_date:
            current_date = event_date
            if isinstance(event_date, date):
                lines.append(f"\n{event_date.strftime('%A, %B %d, %Y')}:")

        if event.all_day:
            time_str = "All day"
        else:
            start_str = event.start.strftime("%-I:%M %p")
            end_str = event.end.strftime("%-I:%M %p")
            time_str = f"{start_str}–{end_str}"

        line = f"  {time_str}  {event.title}"
        if event.location:
            line += f" ({event.location})"
        lines.append(line)

    return "\n".join(lines).strip()
