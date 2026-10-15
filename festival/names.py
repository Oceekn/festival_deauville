"""Names are stored without the spaces around them.

Artists and venues are found by a slug: lower case ASCII letters, digits
and single dashes, with accents removed.
"""

import re
import unicodedata

from festival.errors import InvalidError

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_LIGATURES = str.maketrans({"œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae"})


def require_text(value: object, what: str) -> str:
    """Return the text without surrounding spaces, or explain why it is refused."""
    if not isinstance(value, str):
        raise InvalidError(f"The {what} must be text.")
    cleaned = value.strip()
    if not cleaned:
        raise InvalidError(f"The {what} cannot be empty.")
    return cleaned


def slugify(name: str) -> str:
    """Turn a name into its slug. 'Élodie Marchal !' becomes 'elodie-marchal'."""
    text = unicodedata.normalize("NFKD", name.translate(_LIGATURES))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return _NOT_SLUG.sub("-", text).strip("-")


def join_names(names: list[str]) -> str:
    """Join names the way a programme line does: 'A, B and C'."""
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + " and " + names[-1]
