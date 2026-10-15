"""The three kinds of performances.

Solo, Lineup and Workshop share a title, a venue, a start and a duration.
Each kind adds who is on stage, and checks its own rules. Rules that need
the whole programme (a free slot, a festival day) live on Festival.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

from festival.artist import Artist
from festival.clock import format_moment, programme_day
from festival.errors import ConflictError, InvalidError
from festival.names import join_names, require_text
from festival.venue import Venue

MINUTES_PER_ACT = 10
BREAK_BETWEEN_ACTS = 3


class Performance(ABC):
    """What every show shares."""

    kind: str

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: datetime,
        duration_minutes: int,
        description: str = "",
    ) -> None:
        self.title = require_text(title, "title")
        self.venue = venue
        self.start = start
        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
            raise InvalidError("A duration must be a whole number.")
        if not 1 <= duration_minutes <= 360:
            raise InvalidError(
                f"{self.title} must last between 1 and 360 minutes, "
                f"not {duration_minutes}."
            )
        self.duration_minutes = duration_minutes
        if not isinstance(description, str):
            raise InvalidError("The description must be text.")
        self.description = description.strip()

    @property
    def end(self) -> datetime:
        """The moment the show ends."""
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def festival_day(self) -> date:
        """The programme day, which ends at 06:00."""
        return programme_day(self.start)

    @property
    def id(self) -> str:
        """Venue slug plus the start, for example le-kiosque-2027-06-12-0100."""
        return f"{self.venue.slug}-{self.start.strftime('%Y-%m-%d-%H%M')}"

    @property
    def capacity(self) -> int:
        """Seats for a show. A workshop overrides this with its number of places."""
        return self.venue.capacity

    @abstractmethod
    def on_stage(self) -> list[Artist]:
        """Artists on stage, in order of appearance."""

    @abstractmethod
    def summary(self) -> str:
        """One line for the programme."""

    @abstractmethod
    def saved_details(self) -> dict[str, object]:
        """Fields that are stored, and that depend on the kind."""

    def details(self) -> dict[str, object]:
        """Fields the API adds for this kind."""
        return dict(self.saved_details())

    def to_public(self) -> dict[str, object]:
        """Return the show as the website and the admin read it."""
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "venue_name": self.venue.name,
            "start": format_moment(self.start),
            "end": format_moment(self.end),
            "duration_minutes": self.duration_minutes,
            "festival_day": self.festival_day.isoformat(),
            "description": self.description,
            "summary": self.summary(),
            "capacity": self.capacity,
            "artists": [
                {"slug": artist.slug, "name": artist.name} for artist in self.on_stage()
            ],
        }
        data.update(self.details())
        return data

    def to_saved(self) -> dict[str, object]:
        """Return the show as it is stored in the file."""
        data: dict[str, object] = {
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "start": format_moment(self.start),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
        }
        data.update(self.saved_details())
        return data


class Solo(Performance):
    """One artist, and a minimum age for the audience, from 0 to 18."""

    kind = "solo"

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: datetime,
        duration_minutes: int,
        artist: Artist,
        min_age: int,
        description: str = "",
    ) -> None:
        super().__init__(title, venue, start, duration_minutes, description)
        if isinstance(min_age, bool) or not isinstance(min_age, int):
            raise InvalidError("The minimum age must be a whole number.")
        if not 0 <= min_age <= 18:
            raise InvalidError(
                f"The minimum age of {self.title} must be between 0 and 18, "
                f"not {min_age}."
            )
        self.artist = artist
        self.min_age = min_age

    def on_stage(self) -> list[Artist]:
        return [self.artist]

    def summary(self) -> str:
        if self.min_age > 0:
            return f"{self.artist.name} ({self.min_age}+)"
        return self.artist.name

    def saved_details(self) -> dict[str, object]:
        return {"artist": self.artist.slug, "min_age": self.min_age}


class Lineup(Performance):
    """A host, then acts one after another.

    Each act needs 10 minutes, and the host needs 3 minutes between two acts.
    Three acts therefore last at least 3 x 10 + 2 x 3 = 36 minutes.
    """

    kind = "lineup"

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: datetime,
        duration_minutes: int,
        host: Artist,
        acts: list[Artist],
        description: str = "",
    ) -> None:
        super().__init__(title, venue, start, duration_minutes, description)
        if len(acts) < 2:
            raise InvalidError(f"{self.title} needs at least 2 acts.")
        seen: set[str] = set()
        for act in acts:
            if act.slug in seen:
                raise InvalidError(f"{act.name} appears twice in {self.title}.")
            seen.add(act.slug)
        if host.slug in seen:
            raise InvalidError(
                f"{host.name} hosts {self.title} and cannot also be an act."
            )
        minimum = len(acts) * MINUTES_PER_ACT + (len(acts) - 1) * BREAK_BETWEEN_ACTS
        if self.duration_minutes < minimum:
            raise InvalidError(
                f"A lineup of {len(acts)} acts lasts at least {minimum} minutes."
            )
        self.host = host
        self.acts = list(acts)

    def on_stage(self) -> list[Artist]:
        return [self.host, *self.acts]

    def summary(self) -> str:
        names = join_names([act.name for act in self.acts])
        return f"hosted by {self.host.name}, with {names}"

    def saved_details(self) -> dict[str, object]:
        return {
            "host": self.host.slug,
            "acts": [act.slug for act in self.acts],
        }


class Workshop(Performance):
    """A teacher, and participants who register by name until the room is full.

    The number of places is the smaller of max_participants and the seats
    of the venue. 'Camille R.' and 'camille r.' are the same participant.
    """

    kind = "workshop"

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: datetime,
        duration_minutes: int,
        teacher: Artist,
        max_participants: int,
        participants: list[str] | None = None,
        description: str = "",
    ) -> None:
        super().__init__(title, venue, start, duration_minutes, description)
        if isinstance(max_participants, bool) or not isinstance(max_participants, int):
            raise InvalidError("A number of places must be a whole number.")
        if max_participants < 1:
            raise InvalidError(
                f"{self.title} needs at least 1 place, not {max_participants}."
            )
        self.teacher = teacher
        self.max_participants = max_participants
        self.participants: list[str] = []
        for name in participants or []:
            self.register(name)

    @property
    def capacity(self) -> int:
        return min(self.max_participants, self.venue.capacity)

    @property
    def places_left(self) -> int:
        return self.capacity - len(self.participants)

    def on_stage(self) -> list[Artist]:
        return [self.teacher]

    def summary(self) -> str:
        return f"taught by {self.teacher.name}"

    def saved_details(self) -> dict[str, object]:
        return {
            "teacher": self.teacher.slug,
            "max_participants": self.max_participants,
            "participants": list(self.participants),
        }

    def details(self) -> dict[str, object]:
        data = self.saved_details()
        data["places_left"] = self.places_left
        return data

    def register(self, name: object) -> str:
        """Register a name, kept as written, without surrounding spaces."""
        clean = require_text(name, "participant name")
        for existing in self.participants:
            if existing.casefold() == clean.casefold():
                raise ConflictError(
                    f"{existing} is already registered for {self.title}."
                )
        if len(self.participants) >= self.capacity:
            raise ConflictError(f"{self.title} is full ({self.capacity} places).")
        self.participants.append(clean)
        return clean
