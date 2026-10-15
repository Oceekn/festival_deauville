# Deauville Festival du Rire

Programme of the 2027 edition: venues, artists and three kinds of shows.
The public website and the admin are the HTML in `web/`. This project is
the part they talk to: the rules, the JSON file, a command line and a
small web API.

## Install and run

```bash
uv sync
```

One festival day, in order. A show after midnight stays on the previous day:

```bash
uv run main.py programme 2027-06-11
```

Artists, with how many shows each of them plays:

```bash
uv run main.py artists
```

What is on stage at a given moment, and the next 3 shows:

```bash
uv run main.py now --at 2027-06-11T21:00
```

Website, admin and API:

```bash
uv run main.py serve
```

- site: http://127.0.0.1:8000/
- admin: http://127.0.0.1:8000/admin/
- docs: http://127.0.0.1:8000/docs

Tests, style and the package:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv build
```

## Structure

| File | Role |
| --- | --- |
| `festival/venue.py`, `artist.py` | a room, a person, and the slug of their name |
| `festival/performance.py` | what every show shares, then Solo, Lineup and Workshop |
| `festival/festival.py` | the programme, and the rules that need the whole edition |
| `festival/clock.py` | a festival day ends at 06:00 |
| `festival/names.py` | trim a name, build a slug |
| `festival/errors.py` | a sentence an organiser can read, and which rule broke |
| `festival/storage.py` | the only file that reads and writes JSON |
| `festival/cli.py`, `api.py` | they call the model, they do not re-check the rules |

### Which objects, and what each one checks

- A **Venue** checks its name, its address and that it has at least one seat.
- An **Artist** checks the name. The slug is the identity: `Élodie Marchal !`
  and `Elodie Marchal` are the same artist.
- A **Performance** checks the title, the duration (1 to 360 minutes) and the
  description. **Solo** adds the minimum age (0 to 18). **Lineup** adds the
  host, at least two different acts, and the minimum length: each act needs
  10 minutes and the host needs 3 minutes between two acts, so three acts
  last at least 36 minutes. **Workshop** adds the teacher, the number of
  places, and registration. Names are compared without case, and the places
  are `min(max_participants, seats)`.
- The **Festival** checks the rules that need the other shows: the day is
  inside the edition, the venue has 30 minutes free, and every artist on
  stage has 30 minutes free, whatever their role.

### Where a rule lives

In the model, not in the command line and not in the API. The lists of
venues, artists and shows are private. The only way in is
`add_performance`, `replace_performance`, `cancel_performance` and
`register_participant`. Each one checks first and changes the programme
only if every rule holds. A move onto a busy slot leaves the show where
it was.

The caller knows which rule broke from the class of the error:
`NotFoundError` (404), `ConflictError` (409), `InvalidError` (422).
The message is the sentence. `StorageError` means the file cannot be read
or written (500). Loading the file builds the same objects, so a broken
file gives that sentence instead of a traceback.

### If the JSON file became a database

`storage.py` would be rewritten. The model would not change: it never
opens the file. `cli.py` and `api.py` would only change the line that
builds `JsonStorage`.

## What is done, and what is not

Done: the model and the rules, JSON load and save, the command line, the
FastAPI routes of `API.md`, the website and the admin, tests, types,
docstrings, and a clean `ruff` run.

Not done: a second storage in SQLite. The place for it is `storage.py`.
