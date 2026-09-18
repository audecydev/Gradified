class ScoringError(Exception):
    """Base class for expected scoring-domain failures."""


class InvalidScoringValueError(ScoringError):
    """Raised when a numeric scoring value is malformed or unauthorized."""


class ScoringNumericEnvelopeError(ScoringError):
    """Raised when a valid numeric representation exceeds Numeric Profile v1."""


class ScoreOutOfRangeError(ScoringError):
    """Raised when the final score lies outside the permitted academic range."""


class InvalidCriterionJudgmentError(ScoringError):
    """Raised when evaluator/judgment input is invalid for scoring."""


class InvalidScoringAuthorityError(ScoringError):
    """Raised when immutable scoring authority is structurally invalid."""


class InvalidRuleError(InvalidScoringAuthorityError):
    """Raised when a scoring rule is malformed or invalid as authority."""


class DependencyCycleError(InvalidRuleError):
    """Raised when positive-credit dependencies form a cycle."""


class UnsupportedScoringSemanticsError(InvalidScoringAuthorityError):
    """Raised when scoring authority requests unsupported reducer semantics."""


class UnknownCriterionError(ScoringError):
    """Semantic category for an unknown criterion reference."""


class UnknownPerformanceLevelError(ScoringError):
    """Semantic category for an unknown performance-level reference."""


class UnknownAuthorityCriterionError(
    InvalidScoringAuthorityError,
    UnknownCriterionError,
):
    """Raised when immutable scoring authority references an unknown criterion."""


class UnknownAuthorityPerformanceLevelError(
    InvalidScoringAuthorityError,
    UnknownPerformanceLevelError,
):
    """Raised when immutable scoring authority references an unknown level."""


class UnknownJudgmentCriterionError(
    InvalidCriterionJudgmentError,
    UnknownCriterionError,
):
    """Raised when evaluator/judgment input references an unknown criterion."""


class UnknownJudgmentPerformanceLevelError(
    InvalidCriterionJudgmentError,
    UnknownPerformanceLevelError,
):
    """Raised when evaluator/judgment input references an unknown level."""


class DuplicateJudgmentError(InvalidCriterionJudgmentError):
    """Raised when more than one judgment is supplied for one atomic criterion."""


class MissingJudgmentError(InvalidCriterionJudgmentError):
    """Raised when an atomic criterion has no supplied judgment."""


class InvalidPaperAggregationInputError(ScoringError):
    """Raised when admitted question results are invalid for paper aggregation."""
