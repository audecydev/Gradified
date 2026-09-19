from __future__ import annotations


class RubricAuthoringError(Exception):
    """Base class for expected rubric-authoring domain failures."""


class InvalidRubricAuthoringInputError(RubricAuthoringError):
    """Raised when an authoring domain object has the wrong runtime shape."""


class RubricResourceLimitError(RubricAuthoringError):
    """Raised when authoring processing exceeds explicit structural limits."""

    def __init__(self, message: str, *, issues: object | None = None) -> None:
        super().__init__(message)
        self.issues = issues


class RubricCompilationError(RubricAuthoringError):
    """Raised when lint errors prevent deterministic compilation."""

    def __init__(self, message: str, *, lint_result: object | None = None) -> None:
        super().__init__(message)
        self.lint_result = lint_result


class RubricLifecycleError(RubricAuthoringError):
    """Raised when an immutable rubric version transition is invalid."""


class NoMeaningfulRubricChangeError(RubricLifecycleError):
    """Raised when a requested revision has identical canonical content."""
