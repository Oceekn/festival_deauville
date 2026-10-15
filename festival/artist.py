"""A person who can be on stage."""

from festival.errors import InvalidError
from festival.names import require_text, slugify


class Artist:
    """An artist is identified by the slug of their name.

    'Élodie Marchal !' and 'Elodie Marchal' are the same artist, because
    both slugs are 'elodie-marchal'.
    """

    def __init__(self, name: str, bio: str = "", photo_url: str = "") -> None:
        self.name = require_text(name, "name")
        self.slug = slugify(self.name)
        if not self.slug:
            raise InvalidError(f"'{self.name}' cannot be used as a name.")
        if not isinstance(bio, str) or not isinstance(photo_url, str):
            raise InvalidError("The bio and the photo must be text.")
        self.bio = bio.strip()
        self.photo_url = photo_url.strip()

    def to_public(self) -> dict[str, str]:
        """Return the artist as the API shows them."""
        return {
            "slug": self.slug,
            "name": self.name,
            "bio": self.bio,
            "photo_url": self.photo_url,
        }

    def to_saved(self) -> dict[str, str]:
        """Return the artist as they are stored in the file."""
        return {
            "name": self.name,
            "bio": self.bio,
            "photo_url": self.photo_url,
        }
