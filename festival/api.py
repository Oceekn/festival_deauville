"""HTTP API, the public website and the admin.

This module translates requests into calls on Festival. It does not decide
whether a show is allowed: the model does. A FestivalError becomes the
status listed in API.md. A broken file becomes a 500.
"""

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from festival.clock import format_moment, parse_moment
from festival.errors import (
    ConflictError,
    FestivalError,
    InvalidError,
    NotFoundError,
    StorageError,
)
from festival.festival import Festival
from festival.storage import DEFAULT_DATA, JsonStorage

ROOT = Path(__file__).resolve().parent.parent


class ArtistIn(BaseModel):
    """Body of POST /api/artists."""

    name: str
    bio: str = ""
    photo_url: str = ""


class _ShowIn(BaseModel):
    title: str
    venue: str
    start: datetime
    duration_minutes: int
    description: str = ""


class SoloIn(_ShowIn):
    """A solo show."""

    kind: Literal["solo"]
    artist: str
    min_age: int


class LineupIn(_ShowIn):
    """A lineup."""

    kind: Literal["lineup"]
    host: str
    acts: list[str]


class WorkshopIn(_ShowIn):
    """A workshop."""

    kind: Literal["workshop"]
    teacher: str
    max_participants: int
    participants: list[str] = Field(default_factory=list)


class ParticipantIn(BaseModel):
    """Body of a registration."""

    name: str


ShowIn = Annotated[SoloIn | LineupIn | WorkshopIn, Field(discriminator="kind")]


def create_app(data_path: Path | None = None) -> FastAPI:
    """Build the server. data_path defaults to data/festival.json."""
    app = FastAPI(title="Deauville Festival du Rire")
    app.state.storage = JsonStorage(data_path or DEFAULT_DATA)
    app.state.festival = None

    app.get("/api/festival")(read_festival)
    app.get("/api/venues")(read_venues)
    app.get("/api/artists")(read_artists)
    app.get("/api/artists/{slug}")(read_artist)
    app.get("/api/programme")(read_programme)
    app.get("/api/performances/{performance_id}")(read_performance)
    app.get("/api/now")(read_now)
    app.post("/api/artists", status_code=201)(create_artist)
    app.post("/api/performances", status_code=201)(create_performance)
    app.put("/api/performances/{performance_id}")(update_performance)
    app.delete("/api/performances/{performance_id}", status_code=204)(
        delete_performance
    )
    app.post("/api/performances/{performance_id}/participants", status_code=201)(
        create_participant
    )

    for error, status in (
        (NotFoundError, 404),
        (ConflictError, 409),
        (InvalidError, 422),
        (StorageError, 500),
    ):
        app.add_exception_handler(error, _message(status))

    app.mount(
        "/admin", StaticFiles(directory=ROOT / "web" / "admin", html=True), name="admin"
    )
    app.mount(
        "/", StaticFiles(directory=ROOT / "web" / "public", html=True), name="site"
    )
    return app


def read_festival(request: Request) -> dict:
    """Name, first day, last day and the list of festival days."""
    return _festival(request).info()


def read_venues(request: Request) -> list:
    """Venues, in the order they were added."""
    return [venue.to_public() for venue in _festival(request).venues()]


def read_artists(request: Request) -> list:
    """Artists, in alphabetical order of their slug."""
    return [artist.to_public() for artist in _festival(request).artists()]


def read_artist(slug: str, request: Request) -> dict:
    """One artist and their shows."""
    festival = _festival(request)
    artist = festival.require_artist(slug)
    data = artist.to_public()
    data["performances"] = [show.to_public() for show in festival.shows_of(artist)]
    return data


def read_programme(
    request: Request, day: date | None = None, venue: str | None = None
) -> list:
    """Shows in programme order. Filter with day and venue."""
    return [show.to_public() for show in _festival(request).programme(day, venue)]


def read_performance(performance_id: str, request: Request) -> dict:
    """One show."""
    return _festival(request).require_performance(performance_id).to_public()


def read_now(request: Request, at: datetime | None = None) -> dict:
    """What is on stage, and the next three shows. `at` replaces the clock."""
    moment = parse_moment(at) if at is not None else _this_minute()
    playing, upcoming = _festival(request).on_stage_at(moment)
    return {
        "at": format_moment(moment),
        "now_playing": [show.to_public() for show in playing],
        "up_next": [show.to_public() for show in upcoming],
    }


def create_artist(body: ArtistIn, request: Request) -> dict:
    """Add an artist and save the file."""

    def change(festival: Festival) -> dict:
        artist = festival.add_artist(body.name, body.bio, body.photo_url)
        return artist.to_public()

    return _commit(request, change)


def create_performance(body: ShowIn, request: Request) -> dict:
    """Schedule a show and save the file."""

    def change(festival: Festival) -> dict:
        return festival.add_performance(body.model_dump()).to_public()

    return _commit(request, change)


def update_performance(performance_id: str, body: ShowIn, request: Request) -> dict:
    """Replace a show. If a rule refuses it, the old one stays."""

    def change(festival: Festival) -> dict:
        show = festival.replace_performance(performance_id, body.model_dump())
        return show.to_public()

    return _commit(request, change)


def delete_performance(performance_id: str, request: Request) -> Response:
    """Cancel a show and save the file."""

    def change(festival: Festival) -> None:
        festival.cancel_performance(performance_id)

    _commit(request, change)
    return Response(status_code=204)


def create_participant(
    performance_id: str, body: ParticipantIn, request: Request
) -> dict:
    """Register a participant on a workshop and save the file."""

    def change(festival: Festival) -> dict:
        workshop = festival.register_participant(performance_id, body.name)
        return workshop.to_public()

    return _commit(request, change)


def _festival(request: Request) -> Festival:
    festival = request.app.state.festival
    if festival is None:
        festival = request.app.state.storage.load()
        request.app.state.festival = festival
    return festival


def _commit(request: Request, change: Callable[[Festival], object]) -> object:
    """Apply a change and save it. If anything refuses, the festival is unchanged."""
    festival = _festival(request)
    snapshot = festival.to_dict()
    try:
        result = change(festival)
    except FestivalError:
        request.app.state.festival = Festival.from_dict(snapshot)
        raise
    try:
        request.app.state.storage.save(festival)
    except StorageError:
        request.app.state.festival = Festival.from_dict(snapshot)
        raise
    return result


def _this_minute() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def _message(status: int):
    def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    return handler


app = create_app()
