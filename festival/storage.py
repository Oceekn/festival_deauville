"""Load and save the festival.

This is the only module that knows the data is a JSON file. The model
checks the rules again on every load. A broken file raises StorageError
with a sentence, not a traceback.
"""

import json
from pathlib import Path

from festival.errors import FestivalError, StorageError
from festival.festival import Festival

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "festival.json"


class JsonStorage:
    """The festival stored in one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Festival:
        """Read the file and check every rule."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as error:
            raise StorageError(
                f"Cannot read {self.path.name}: {error.strerror}."
            ) from error
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise StorageError("The festival file is not valid JSON.") from error
        try:
            return Festival.from_dict(data)
        except FestivalError as error:
            raise StorageError(str(error)) from error

    def save(self, festival: Festival) -> None:
        """Write the festival back. The previous file is replaced only at the end."""
        payload = json.dumps(festival.to_dict(), indent=2, ensure_ascii=False) + "\n"
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(self.path)
        except OSError as error:
            raise StorageError(
                f"Cannot write {self.path.name}: {error.strerror}."
            ) from error
