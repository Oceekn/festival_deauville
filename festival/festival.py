"""The festival: venues, artists, performances, and the programme rules.

A caller cannot put a show in the programme by editing a list. add_performance,
replace_performance, cancel_performance and register_participant are the only
doors, and each one checks the rules before it changes anything.
"""

from datetime import date, datetime, timedelta

from festival.artist import Artist
from festival.clock import format_slot, parse_moment, programme_day
from festival.errors import ConflictError, InvalidError, NotFoundError
from festival.names import require_text
from festival.performance import Lineup, Performance, Solo, Workshop
from festival.venue import Venue

BREAK = timedelta(minutes=30)


class Festival:
    """One edition of the festival.

    Venues stay in the order they were added. Artists are listed by slug.
    Performances are listed by start time, then by venue name.
    """

    def __init__(self, name: str, first_day: date, last_day: date) -> None:
        if not isinstance(name, str) or not name.strip():
            raise InvalidError("The festival name cannot be empty.")
        if first_day > last_day:
            raise InvalidError("The festival ends before it starts.")
        self.name = name.strip()
        self.first_day = first_day
        self.last_day = last_day
        self._venues: list[Venue] = []
        self._artists: list[Artist] = []
        self._performances: list[Performance] = []

    def add_venue(self, name: str, capacity: int, address: str) -> Venue:
        """Add a venue. The same slug cannot be added twice."""
        venue = Venue(name, capacity, address)
        if self._venue(venue.slug) is not None:
            raise ConflictError(f"A venue named {venue.name} already exists.")
        self._venues.append(venue)
        return venue

    def add_artist(self, name: str, bio: str = "", photo_url: str = "") -> Artist:
        """Add an artist. The same slug is the same artist, and is refused."""
        artist = Artist(name, bio, photo_url)
        existing = self._artist(artist.slug)
        if existing is not None:
            raise ConflictError(f"An artist named {existing.name} already exists.")
        self._artists.append(artist)
        return artist

    def add_performance(self, raw: dict) -> Performance:
        """Add a show. Nothing is stored if a rule refuses it."""
        show = self._build(raw)
        self._accept(show)
        self._performances.append(show)
        return show

    def replace_performance(self, performance_id: str, raw: dict) -> Performance:
        """Replace a show, even in another venue or at another time.

        The id follows the venue and the start. If the new version breaks a
        rule, the old show stays where it was.
        """
        old = self.require_performance(performance_id)
        show = self._build(raw)
        self._accept(show, ignoring=old)
        self._performances[self._performances.index(old)] = show
        return show

    def cancel_performance(self, performance_id: str) -> None:
        """Remove a show from the programme."""
        show = self.require_performance(performance_id)
        self._performances.remove(show)

    def register_participant(self, performance_id: str, name: str) -> Workshop:
        """Register a name on a workshop."""
        show = self.require_performance(performance_id)
        if not isinstance(show, Workshop):
            raise InvalidError(f"{show.title} is not a workshop.")
        show.register(name)
        return show

    def venues(self) -> list[Venue]:
        """Venues, in the order they were added."""
        return list(self._venues)

    def artists(self) -> list[Artist]:
        """Artists, in alphabetical order of their slug."""
        return sorted(self._artists, key=lambda artist: artist.slug)

    def performances(self) -> list[Performance]:
        """Shows, by start time, then by venue name."""
        return sorted(
            self._performances, key=lambda show: (show.start, show.venue.name)
        )

    def programme(
        self, day: date | None = None, venue: str | None = None
    ) -> list[Performance]:
        """The programme, optionally one festival day and one venue."""
        shows = self.performances()
        if day is not None:
            shows = [show for show in shows if show.festival_day == day]
        if venue:
            self.require_venue(venue)
            shows = [show for show in shows if show.venue.slug == venue]
        return shows

    def shows_of(self, artist: Artist) -> list[Performance]:
        """Every show where this artist is on stage, in programme order."""
        return [
            show
            for show in self.performances()
            if any(person.slug == artist.slug for person in show.on_stage())
        ]

    def on_stage_at(
        self, moment: datetime
    ) -> tuple[list[Performance], list[Performance]]:
        """Shows playing at this moment, and the next three that have not started."""
        ordered = self.performances()
        playing = [show for show in ordered if show.start <= moment < show.end]
        upcoming = [show for show in ordered if show.start > moment][:3]
        return playing, upcoming

    def info(self) -> dict[str, object]:
        """Name, dates, and the list of festival days."""
        days: list[str] = []
        day = self.first_day
        while day <= self.last_day:
            days.append(day.isoformat())
            day += timedelta(days=1)
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "days": days,
        }

    def require_venue(self, slug: str) -> Venue:
        """Return the venue, or explain that it does not exist."""
        venue = self._venue(slug)
        if venue is None:
            raise NotFoundError(f"Unknown venue '{slug}'.")
        return venue

    def require_artist(self, slug: str) -> Artist:
        """Return the artist, or explain that they do not exist."""
        artist = self._artist(slug)
        if artist is None:
            raise NotFoundError(f"Unknown artist '{slug}'.")
        return artist

    def require_performance(self, performance_id: str) -> Performance:
        """Return the show, or explain that it does not exist."""
        for show in self._performances:
            if show.id == performance_id:
                return show
        raise NotFoundError(f"Unknown performance '{performance_id}'.")

    def to_dict(self) -> dict[str, object]:
        """Return the whole festival as it is stored."""
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "venues": [venue.to_saved() for venue in self._venues],
            "artists": [artist.to_saved() for artist in self._artists],
            "performances": [show.to_saved() for show in self.performances()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Festival":
        """Build a festival from stored data, and check every rule again."""
        if not isinstance(data, dict):
            raise InvalidError("The festival file must contain an object.")
        try:
            first_day = date.fromisoformat(str(data["first_day"]))
            last_day = date.fromisoformat(str(data["last_day"]))
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidError(
                "The festival needs a first day and a last day, like 2027-06-10."
            ) from error
        festival = cls(str(data.get("name", "")), first_day, last_day)
        for raw in _as_list(data.get("venues", []), "venues"):
            festival.add_venue(
                _text(raw, "name", "name"),
                _whole(raw, "capacity", "A number of seats"),
                _text(raw, "address", "address"),
            )
        for raw in _as_list(data.get("artists", []), "artists"):
            festival.add_artist(
                _text(raw, "name", "name"),
                _optional_text(raw, "bio"),
                _optional_text(raw, "photo_url"),
            )
        for raw in _as_list(data.get("performances", []), "performances"):
            festival.add_performance(raw)
        return festival

    def _venue(self, slug: str) -> Venue | None:
        for venue in self._venues:
            if venue.slug == slug:
                return venue
        return None

    def _artist(self, slug: str) -> Artist | None:
        for artist in self._artists:
            if artist.slug == slug:
                return artist
        return None

    def _build(self, raw: dict) -> Performance:
        """Turn a stored show into an object. This checks the rules of its kind."""
        if not isinstance(raw, dict):
            raise InvalidError("A performance must be an object.")
        kind = raw.get("kind")
        venue = self.require_venue(_text(raw, "venue", "venue"))
        title = raw.get("title", "")
        start = parse_moment(raw.get("start"))
        duration = _whole(raw, "duration_minutes", "A duration")
        description = _optional_text(raw, "description")
        if kind == "solo":
            return Solo(
                title,
                venue,
                start,
                duration,
                self.require_artist(_text(raw, "artist", "artist")),
                _whole(raw, "min_age", "A minimum age"),
                description,
            )
        if kind == "lineup":
            acts = [
                self.require_artist(_slug(item, "act"))
                for item in _as_list(raw.get("acts"), "acts")
            ]
            return Lineup(
                title,
                venue,
                start,
                duration,
                self.require_artist(_text(raw, "host", "host")),
                acts,
                description,
            )
        if kind == "workshop":
            names = _as_list(raw.get("participants", []), "participants")
            return Workshop(
                title,
                venue,
                start,
                duration,
                self.require_artist(_text(raw, "teacher", "teacher")),
                _whole(raw, "max_participants", "A number of places"),
                names,
                description,
            )
        if kind is None:
            raise InvalidError("A performance kind is solo, lineup or workshop.")
        raise InvalidError(f"Kind '{kind}' is not solo, lineup or workshop.")

    def _accept(self, show: Performance, ignoring: Performance | None = None) -> None:
        """Check the rules that need the whole programme. Raise before any change."""
        day = programme_day(show.start)
        if not self.first_day <= day <= self.last_day:
            raise ConflictError(
                f"{show.title} is on {day.isoformat()}, outside the festival "
                f"({self.first_day.isoformat()} to {self.last_day.isoformat()})."
            )
        others = [item for item in self._performances if item is not ignoring]
        for other in others:
            if other.id == show.id:
                raise ConflictError(
                    f"{show.venue.name} already has a show at "
                    f"{show.start.strftime('%Y-%m-%d %H:%M')}."
                )
            if not _too_close(show, other):
                continue
            if other.venue.slug == show.venue.slug:
                raise ConflictError(
                    f"{show.venue.name} is busy with {other.title} "
                    f"({format_slot(other.start, other.end)}). "
                    "Leave 30 minutes between two shows."
                )
            shared = _shared_artist(show, other)
            if shared is not None:
                raise ConflictError(
                    f"{shared.name} is busy with {other.title} "
                    f"({format_slot(other.start, other.end)}). "
                    "Leave 30 minutes between two shows."
                )


def _too_close(first: Performance, second: Performance) -> bool:
    earlier, later = (first, second) if first.start <= second.start else (second, first)
    return later.start < earlier.end + BREAK


def _shared_artist(first: Performance, second: Performance) -> Artist | None:
    slugs = {artist.slug for artist in second.on_stage()}
    for artist in first.on_stage():
        if artist.slug in slugs:
            return artist
    return None


def _as_list(value: object, what: str) -> list:
    if not isinstance(value, list):
        raise InvalidError(f"The {what} must be a list.")
    return value


def _text(raw: object, key: str, what: str) -> str:
    if not isinstance(raw, dict) or key not in raw:
        raise InvalidError(f"The {what} is required.")
    return require_text(raw[key], what)


def _optional_text(raw: object, key: str) -> str:
    if not isinstance(raw, dict):
        return ""
    value = raw.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidError(f"The {key} must be text.")
    return value


def _whole(raw: object, key: str, what: str) -> int:
    if not isinstance(raw, dict) or key not in raw or raw[key] is None:
        raise InvalidError(f"{what} is required.")
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidError(f"{what} must be a whole number.")
    return value


def _slug(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidError(f"Each {what} must be an artist.")
    return value.strip()
