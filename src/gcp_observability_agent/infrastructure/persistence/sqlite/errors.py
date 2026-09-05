"""Persistence-specific failures that do not leak SQLite implementation details."""


class PersistenceError(RuntimeError):
    """Base class for persistence failures."""


class ConcurrencyConflict(PersistenceError):
    """Raised when an aggregate version no longer matches durable state."""

