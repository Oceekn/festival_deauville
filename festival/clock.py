"""Local festival time.

A festival day ends at 06:00. A show starting at 00:30 on 12 June belongs
to the programme of 11 June. Times have no time zone.
"""

from datetime import date, datetime, timedelta

from festival.errors import InvalidError

DAY_ENDS_HOUR = 6


def programme_day(start: datetime) -> date:
    """Return the festival day a show belongs to."""
    if start.hour < DAY_ENDS_HOUR:
        return start.date() - timedelta(days=1)
    return start.date()


def parse_moment(value: object) -> datetime:
    """Read a local time such as 2027-06-11T21:00."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError as error:
            raise InvalidError(
                f"'{value}' is not a time like 2027-06-11T21:00."
            ) from error
    else:
        raise InvalidError("A start time is required, like 2027-06-11T21:00.")
    if moment.tzinfo is not None:
        raise InvalidError("A show time is local, with no time zone.")
    return moment.replace(second=0, microsecond=0)


def format_moment(value: datetime) -> str:
    """Format a local time the way the website expects it."""
    return value.strftime("%Y-%m-%dT%H:%M")


def format_slot(start: datetime, end: datetime) -> str:
    """Format a slot the way an organiser reads it: '2027-06-12 01:00-02:00'."""
    left = start.strftime("%Y-%m-%d %H:%M")
    if start.date() == end.date():
        right = end.strftime("%H:%M")
    else:
        right = end.strftime("%Y-%m-%d %H:%M")
    return f"{left}-{right}"
