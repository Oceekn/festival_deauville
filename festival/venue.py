"""A room where a show can happen."""

from festival.errors import InvalidError
from festival.names import require_text, slugify


class Venue:
    """A venue has a name, at least one seat, and an address.

    Two venues with the same slug are the same venue. The slug comes from
    the name: 'Théâtre des Planches' is 'theatre-des-planches'.
    """

    def __init__(self, name: str, capacity: int, address: str) -> None:
        self.name = require_text(name, "name")
        self.slug = slugify(self.name)
        if not self.slug:
            raise InvalidError(f"'{self.name}' cannot be used as a name.")
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise InvalidError("A number of seats must be a whole number.")
        if capacity < 1:
            raise InvalidError(f"{self.name} needs at least 1 seat, not {capacity}.")
        self.capacity = capacity
        self.address = require_text(address, "address")

    def to_public(self) -> dict[str, object]:
        """Return the venue as the API shows it."""
        return {
            "slug": self.slug,
            "name": self.name,
            "capacity": self.capacity,
            "address": self.address,
        }

    def to_saved(self) -> dict[str, object]:
        """Return the venue as it is stored in the file."""
        return {
            "name": self.name,
            "capacity": self.capacity,
            "address": self.address,
        }
