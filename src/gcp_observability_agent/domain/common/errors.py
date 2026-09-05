"""Domain errors for invariant violations."""


class DomainRuleViolation(ValueError):
    """Raised when a domain operation would violate an invariant."""

