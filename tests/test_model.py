"""The rules, checked on the model itself.

The command line and the API are not involved: if a rule holds here,
they cannot bypass it.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from festival.clock import programme_day
from festival.errors import ConflictError, InvalidError, NotFoundError, StorageError
from festival.festival import Festival
from festival.names import slugify
from festival.storage import JsonStorage

DATA = Path(__file__).resolve().parents[1] / "data" / "festival.json"


def festival() -> Festival:
    """A small edition, enough to try each rule."""
    edition = Festival("Test", date(2027, 6, 10), date(2027, 6, 13))
    edition.add_venue("Le Kiosque", 120, "Beach")
    edition.add_venue("La Cabane", 2, "Beach")
    edition.add_artist("Nora Lebrun")
    edition.add_artist("Tom Vasseur")
    edition.add_artist("Hugo Lemaire")
    edition.add_artist("Maya Choukri")
    return edition


def solo(
    title: str = "Show",
    venue: str = "le-kiosque",
    start: str = "2027-06-10T20:00",
    duration: int = 60,
    artist: str = "nora-lebrun",
    min_age: int = 0,
) -> dict:
    return {
        "kind": "solo",
        "title": title,
        "venue": venue,
        "start": start,
        "duration_minutes": duration,
        "artist": artist,
        "min_age": min_age,
    }


def test_slug_removes_accents_and_punctuation() -> None:
    assert slugify("Théâtre des Planches") == "theatre-des-planches"
    assert slugify("Élodie Marchal !") == "elodie-marchal"


def test_a_festival_day_ends_at_six() -> None:
    assert programme_day(datetime(2027, 6, 12, 0, 30)) == date(2027, 6, 11)
    assert programme_day(datetime(2027, 6, 12, 6, 0)) == date(2027, 6, 12)


def test_the_real_festival_loads() -> None:
    edition = JsonStorage(DATA).load()

    assert edition.name == "Deauville Festival du Rire 2027"
    assert len(edition.venues()) == 4
    assert len(edition.artists()) == 12
    assert len(edition.performances()) == 23
    assert [venue.slug for venue in edition.venues()][0] == "grand-casino"
    assert edition.artists()[0].slug == "elodie-marchal"
    assert edition.artists()[0].name == "Élodie Marchal"

    after_hours = edition.require_performance("le-kiosque-2027-06-12-0100")
    assert after_hours.festival_day == date(2027, 6, 11)
    assert after_hours.summary() == (
        "hosted by Tom Vasseur, with Hugo Lemaire and Maya Choukri"
    )

    friday = [show.title for show in edition.programme(day=date(2027, 6, 11))]
    saturday = [show.title for show in edition.programme(day=date(2027, 6, 12))]
    assert "After Hours" in friday
    assert "After Hours" not in saturday

    workshop = edition.require_performance("la-cabane-2027-06-11-1030")
    assert workshop.capacity == 12
    assert workshop.places_left == 9
    assert len(edition.shows_of(edition.require_artist("elodie-marchal"))) == 3


def test_two_spellings_of_a_name_are_the_same_artist() -> None:
    edition = festival()
    edition.add_artist("Élodie Marchal")
    with pytest.raises(ConflictError, match="already exists"):
        edition.add_artist("Elodie Marchal !")


def test_a_name_cannot_be_empty() -> None:
    edition = festival()
    with pytest.raises(InvalidError, match="cannot be empty"):
        edition.add_artist("   ")


def test_a_venue_needs_one_seat() -> None:
    edition = festival()
    with pytest.raises(InvalidError, match="at least 1 seat"):
        edition.add_venue("Nowhere", 0, "Here")


def test_duration_and_age_stay_in_range() -> None:
    edition = festival()
    with pytest.raises(InvalidError, match="between 1 and 360"):
        edition.add_performance(solo(duration=0))
    with pytest.raises(InvalidError, match="between 0 and 18"):
        edition.add_performance(solo(min_age=19))
    assert edition.performances() == []


def test_a_lineup_of_three_acts_lasts_at_least_36_minutes() -> None:
    edition = festival()
    show = {
        "kind": "lineup",
        "title": "Gala",
        "venue": "le-kiosque",
        "start": "2027-06-10T20:00",
        "duration_minutes": 35,
        "host": "tom-vasseur",
        "acts": ["nora-lebrun", "hugo-lemaire", "maya-choukri"],
    }
    with pytest.raises(InvalidError, match="at least 36 minutes"):
        edition.add_performance(show)
    show["duration_minutes"] = 36
    assert edition.add_performance(show).duration_minutes == 36


def test_the_host_is_not_an_act_and_acts_are_unique() -> None:
    edition = festival()
    hosted = {
        "kind": "lineup",
        "title": "Gala",
        "venue": "le-kiosque",
        "start": "2027-06-10T20:00",
        "duration_minutes": 60,
        "host": "tom-vasseur",
        "acts": ["tom-vasseur", "nora-lebrun"],
    }
    with pytest.raises(InvalidError, match="cannot also be an act"):
        edition.add_performance(hosted)
    hosted["acts"] = ["nora-lebrun", "nora-lebrun"]
    with pytest.raises(InvalidError, match="appears twice"):
        edition.add_performance(hosted)
    hosted["acts"] = ["nora-lebrun"]
    with pytest.raises(InvalidError, match="at least 2 acts"):
        edition.add_performance(hosted)


def test_a_venue_needs_30_minutes_and_a_refusal_changes_nothing() -> None:
    edition = festival()
    edition.add_performance(solo("After Hours", start="2027-06-12T01:00"))
    with pytest.raises(ConflictError) as error:
        edition.add_performance(
            solo(
                "Too Soon", start="2027-06-12T02:10", duration=30, artist="tom-vasseur"
            )
        )
    assert str(error.value) == (
        "Le Kiosque is busy with After Hours (2027-06-12 01:00-02:00). "
        "Leave 30 minutes between two shows."
    )
    assert len(edition.performances()) == 1
    edition.add_performance(
        solo("On Time", start="2027-06-12T02:30", duration=30, artist="tom-vasseur")
    )


def test_an_artist_needs_30_minutes_in_any_venue() -> None:
    edition = festival()
    edition.add_performance(
        solo("After Hours", start="2027-06-12T01:00", artist="tom-vasseur")
    )
    with pytest.raises(ConflictError, match="Tom Vasseur is busy with After Hours"):
        edition.add_performance(
            solo(
                "Too Soon",
                venue="la-cabane",
                start="2027-06-12T02:10",
                artist="tom-vasseur",
            )
        )
    assert len(edition.performances()) == 1


def test_a_show_outside_the_festival_is_refused() -> None:
    edition = festival()
    with pytest.raises(ConflictError, match="outside the festival"):
        edition.add_performance(solo(start="2027-06-09T21:00"))
    with pytest.raises(ConflictError, match="outside the festival"):
        edition.add_performance(solo(start="2027-06-14T06:00"))
    kept = edition.add_performance(solo(start="2027-06-14T01:00"))
    assert kept.festival_day == date(2027, 6, 13)


def test_a_failed_move_leaves_the_show_where_it_was() -> None:
    edition = festival()
    edition.add_performance(solo("One"))
    other = edition.add_performance(
        solo("Two", venue="la-cabane", start="2027-06-10T20:00", artist="tom-vasseur")
    )
    with pytest.raises(ConflictError, match="Le Kiosque is busy"):
        edition.replace_performance(other.id, solo("Two", start="2027-06-10T20:10"))
    kept = edition.require_performance(other.id)
    assert kept.venue.slug == "la-cabane"
    assert kept.start == datetime(2027, 6, 10, 20, 0)


def test_a_move_follows_the_venue_and_the_start() -> None:
    edition = festival()
    show = edition.add_performance(solo("One"))
    moved = edition.replace_performance(
        show.id,
        solo("One", venue="la-cabane", start="2027-06-11T15:00", artist="tom-vasseur"),
    )
    assert moved.id == "la-cabane-2027-06-11-1500"
    with pytest.raises(NotFoundError):
        edition.require_performance(show.id)


def test_cancelling_frees_the_slot() -> None:
    edition = festival()
    show = edition.add_performance(solo("One"))
    edition.cancel_performance(show.id)
    edition.add_performance(solo("Two", artist="tom-vasseur"))
    assert [item.title for item in edition.performances()] == ["Two"]


def test_workshop_places_registration_and_full() -> None:
    edition = festival()
    show = edition.add_performance(
        {
            "kind": "workshop",
            "title": "Lab",
            "venue": "la-cabane",
            "start": "2027-06-11T10:00",
            "duration_minutes": 60,
            "teacher": "nora-lebrun",
            "max_participants": 10,
        }
    )
    assert show.capacity == 2
    edition.register_participant(show.id, "Camille R.")
    with pytest.raises(ConflictError, match="Camille R. is already registered"):
        edition.register_participant(show.id, "  camille r. ")
    edition.register_participant(show.id, "Yanis B.")
    with pytest.raises(ConflictError, match="Lab is full"):
        edition.register_participant(show.id, "Lou M.")
    assert show.places_left == 0

    large_room = edition.add_performance(
        {
            "kind": "workshop",
            "title": "Tiny",
            "venue": "le-kiosque",
            "start": "2027-06-11T10:00",
            "duration_minutes": 60,
            "teacher": "tom-vasseur",
            "max_participants": 1,
        }
    )
    assert large_room.capacity == 1


def test_only_a_workshop_takes_registrations() -> None:
    edition = festival()
    show = edition.add_performance(solo("One"))
    with pytest.raises(InvalidError, match="not a workshop"):
        edition.register_participant(show.id, "Camille R.")


def test_the_real_after_hours_message() -> None:
    edition = JsonStorage(DATA).load()
    with pytest.raises(ConflictError) as error:
        edition.add_performance(
            solo(
                "Too Soon",
                start="2027-06-12T02:10",
                duration=30,
                artist="lea-fontaine",
            )
        )
    assert str(error.value) == (
        "Le Kiosque is busy with After Hours (2027-06-12 01:00-02:00). "
        "Leave 30 minutes between two shows."
    )


def test_a_broken_file_explains_the_rule(tmp_path: Path) -> None:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    raw["performances"][0]["duration_minutes"] = 0
    path = tmp_path / "festival.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(StorageError) as error:
        JsonStorage(path).load()
    assert "between 1 and 360" in str(error.value)
    assert "Traceback" not in str(error.value)


def test_invalid_json_is_a_sentence(tmp_path: Path) -> None:
    path = tmp_path / "festival.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(StorageError, match="not valid JSON"):
        JsonStorage(path).load()


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    edition = JsonStorage(DATA).load()
    path = tmp_path / "festival.json"
    JsonStorage(path).save(edition)
    again = JsonStorage(path).load()
    assert [show.id for show in again.performances()] == [
        show.id for show in edition.performances()
    ]
    assert [artist.slug for artist in again.artists()] == [
        artist.slug for artist in edition.artists()
    ]
