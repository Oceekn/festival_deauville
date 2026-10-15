"""Command line for the festival.

programme, artists and now only read the model. serve starts the website.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from festival.clock import format_moment, parse_moment
from festival.errors import FestivalError, InvalidError, StorageError
from festival.festival import Festival
from festival.performance import Performance
from festival.storage import DEFAULT_DATA, JsonStorage


def main(argv: list[str] | None = None) -> int:
    """Run a command. Returns 0 when it worked, 1 when a rule or the file refused."""
    _use_utf8()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            _serve(args.data, args.host, args.port)
            return 0
        festival = JsonStorage(args.data).load()
        if args.command == "programme":
            _programme(festival, args.day)
        elif args.command == "artists":
            _artists(festival)
        elif args.command == "now":
            _now(festival, args.at)
    except (FestivalError, StorageError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deauville Festival du Rire")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="festival.json")
    commands = parser.add_subparsers(dest="command", required=True)

    programme = commands.add_parser("programme", help="one festival day, in order")
    programme.add_argument("day", help="festival day, like 2027-06-11")

    commands.add_parser("artists", help="artists and how many shows they play")

    now = commands.add_parser("now", help="what is on stage, and the next 3 shows")
    now.add_argument("--at", help="moment like 2027-06-11T21:00 (default: now)")

    serve = commands.add_parser("serve", help="website, admin and API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def _programme(festival: Festival, day_text: str) -> None:
    try:
        day = date.fromisoformat(day_text)
    except ValueError as error:
        raise InvalidError(f"'{day_text}' is not a day like 2027-06-11.") from error
    shows = festival.programme(day=day)
    print(festival.name)
    print(_format_day(day))
    print()
    if not shows:
        print("No performance.")
        return
    for show in shows:
        print(_format_show(show))
        print()


def _artists(festival: Festival) -> None:
    artists = festival.artists()
    width = max((len(artist.name) for artist in artists), default=0)
    print(festival.name)
    print()
    for artist in artists:
        count = len(festival.shows_of(artist))
        noun = "show" if count == 1 else "shows"
        print(f"{artist.name:<{width}}  {count} {noun}")


def _now(festival: Festival, at_text: str | None) -> None:
    if at_text:
        moment = parse_moment(at_text)
    else:
        moment = datetime.now().replace(second=0, microsecond=0)
    playing, upcoming = festival.on_stage_at(moment)
    print(festival.name)
    print(f"At {format_moment(moment).replace('T', ' ')}")
    print()
    print("On stage" if playing else "Nothing on stage")
    for show in playing:
        print(_format_show(show))
        print()
    if playing:
        print()
    print("Up next")
    if not upcoming:
        print("Nothing else.")
        return
    for show in upcoming:
        when = show.start.strftime("%H:%M")
        if show.start.date() != moment.date():
            when = show.start.strftime("%a %H:%M")
        print(f"  {when}  {show.title} - {show.venue.name}")


def _serve(path: Path, host: str, port: int) -> None:
    import uvicorn

    from festival.api import create_app

    JsonStorage(path).load()
    print(f"Website  http://{host}:{port}/")
    print(f"Admin    http://{host}:{port}/admin/")
    print(f"API docs http://{host}:{port}/docs")
    uvicorn.run(create_app(path), host=host, port=port)


def _format_show(show: Performance) -> str:
    start = show.start.strftime("%H:%M")
    if show.start.date() != show.festival_day:
        start = show.start.strftime("%a %H:%M")
    clock = f"{start}-{show.end.strftime('%H:%M')}"
    return f"{clock:<16}{show.title}\n{'':16}{show.venue.name} · {show.summary()}"


def _format_day(day: date) -> str:
    return f"{day.strftime('%A')} {day.day} {day.strftime('%B %Y')}"


def _use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    raise SystemExit(main())
