class ScoringError(Exception):
    """Base class for expected scoring-domain failures."""


class InvalidScoringValueError(ScoringError):
    """Raised when a numeric scoring value is malformed or unauthorized."""