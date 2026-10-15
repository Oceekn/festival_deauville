"""The HTTP contract used by the website and the admin."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from festival.api import create_app

DATA = Path(__file__).resolve().parents[1] / "data" / "festival.json"


@pytest.fixture
def api(tmp_path: Path):
    path = tmp_path / "festival.json"
    shutil.copy(DATA, path)
    with TestClient(create_app(path)) as client:
        yield client, path


def test_reads(api) -> None:
    client, _path = api
    festival = client.get("/api/festival")
    assert festival.status_code == 200
    assert festival.json()["days"] == [
        "2027-06-10",
        "2027-06-11",
        "2027-06-12",
        "2027-06-13",
    ]
    assert client.get("/api/venues").json()[0]["slug"] == "grand-casino"
    assert client.get("/api/artists").json()[0]["slug"] == "elodie-marchal"

    friday = client.get("/api/programme", params={"day": "2027-06-11"}).json()
    assert "After Hours" in [show["title"] for show in friday]
    assert client.get("/api/programme", params={"venue": "nowhere"}).status_code == 404

    artist = client.get("/api/artists/elodie-marchal")
    assert artist.status_code == 200
    assert len(artist.json()["performances"]) == 3
    assert client.get("/api/artists/nobody").status_code == 404
    assert isinstance(client.get("/api/artists/nobody").json()["detail"], str)

    now = client.get("/api/now", params={"at": "2027-06-11T21:00"}).json()
    assert now["at"] == "2027-06-11T21:00"
    assert [show["title"] for show in now["now_playing"]] == ["Tall Tales"]
    assert [show["title"] for show in now["up_next"]] == [
        "Straight Face",
        "Late Laughs",
        "After Hours",
    ]


def test_a_refused_change_does_not_touch_the_file(api) -> None:
    client, path = api
    before = path.read_text(encoding="utf-8")
    response = client.put(
        "/api/performances/le-kiosque-2027-06-13-1500",
        json={
            "kind": "solo",
            "title": "First Time Here",
            "venue": "le-kiosque",
            "start": "2027-06-12T02:10",
            "duration_minutes": 60,
            "artist": "maya-choukri",
            "min_age": 0,
        },
    )
    assert response.status_code == 409
    assert "Leave 30 minutes" in response.json()["detail"]
    assert path.read_text(encoding="utf-8") == before
    kept = client.get("/api/performances/le-kiosque-2027-06-13-1500")
    assert kept.json()["start"] == "2027-06-13T15:00"


def test_move_cancel_and_register(api) -> None:
    client, path = api
    moved = client.put(
        "/api/performances/le-kiosque-2027-06-13-1500",
        json={
            "kind": "solo",
            "title": "First Time Here",
            "venue": "la-cabane",
            "start": "2027-06-13T18:00",
            "duration_minutes": 60,
            "description": "",
            "artist": "maya-choukri",
            "min_age": 0,
        },
    )
    assert moved.status_code == 200
    assert moved.json()["id"] == "la-cabane-2027-06-13-1800"
    assert client.get("/api/performances/le-kiosque-2027-06-13-1500").status_code == 404
    assert "2027-06-13T18:00" in path.read_text(encoding="utf-8")

    assert (
        client.delete("/api/performances/la-cabane-2027-06-13-1800").status_code == 204
    )
    assert client.get("/api/performances/la-cabane-2027-06-13-1800").status_code == 404

    registered = client.post(
        "/api/performances/la-cabane-2027-06-13-1030/participants",
        json={"name": "Camille R."},
    )
    assert registered.status_code == 201
    assert registered.json()["places_left"] == 11
    again = client.post(
        "/api/performances/la-cabane-2027-06-13-1030/participants",
        json={"name": "camille r."},
    )
    assert again.status_code == 409
    refused = client.post(
        "/api/performances/le-kiosque-2027-06-12-0100/participants",
        json={"name": "Camille R."},
    )
    assert refused.status_code == 422
    assert "not a workshop" in refused.json()["detail"]


def test_adding_an_artist(api) -> None:
    client, path = api
    created = client.post("/api/artists", json={"name": "Zoé Martin", "bio": "New."})
    assert created.status_code == 201
    assert created.json()["slug"] == "zoe-martin"
    assert "Zoé Martin" in path.read_text(encoding="utf-8")

    duplicate = client.post("/api/artists", json={"name": "Élodie Marchal"})
    assert duplicate.status_code == 409
    empty = client.post("/api/artists", json={"name": "  "})
    assert empty.status_code == 422
    assert empty.json()["detail"] == "The name cannot be empty."
    missing = client.post("/api/artists", json={})
    assert missing.status_code == 422
    assert isinstance(missing.json()["detail"], list)


def test_pages_and_a_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "festival.json"
    shutil.copy(DATA, path)
    with TestClient(create_app(path)) as client:
        assert "Festival" in client.get("/").text
        assert "Admin" in client.get("/admin/").text

    path.write_text("{", encoding="utf-8")
    with TestClient(create_app(path)) as client:
        response = client.get("/api/festival")
    assert response.status_code == 500
    assert "JSON" in response.json()["detail"]
