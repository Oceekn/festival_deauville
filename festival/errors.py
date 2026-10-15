"""Errors a festival organiser can read.

The message says which rule broke. The web API picks the HTTP status from
the class: not found is 404, a clash is 409, a bad value is 422.
"""


class FestivalError(Exception):
    """A rule of the festival was broken."""


class NotFoundError(FestivalError):
    """An artist, a venue or a performance does not exist."""


class ConflictError(FestivalError):
    """The change clashes with something already in the programme."""


class InvalidError(FestivalError):
    """A value itself is not acceptable."""


class StorageError(Exception):
    """The festival file cannot be read or written."""
