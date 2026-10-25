"""Composition root for admitted CHOICE input (no evaluator permission or scoring).

Other families and execution will be added only through their owned eligibility
and runtime-binding contracts. This entry point does not silently grade.
"""
from __future__ import annotations

from grading.integration.trusted_preparation import PreparationRequest
from grading.integration.authorized_preparation import ProductionPreparationComposer
from grading.integration.choice_authority_admission import (
    AdmittedChoice, ProductionChoiceAdmissionComposer,
)


class ProductionGradingEntry:
    """Trusted application-root entry for the supported PRE→CHOICE admission path."""

    def __init__(self, *, preparation: ProductionPreparationComposer,
                 choices: ProductionChoiceAdmissionComposer) -> None:
        try:
            if type(preparation) is not ProductionPreparationComposer:
                raise TypeError("An installed production preparation composer is required.")
            if type(choices) is not ProductionChoiceAdmissionComposer:
                raise TypeError("An installed production CHOICE admission composer is required.")
        except TypeError as caught:
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None
        self._preparation = preparation
        self._choices = choices

    def prepare_choice(self, *, request: PreparationRequest) -> AdmittedChoice:
        """Return admitted CHOICE inputs; never invoke or publish a grade."""
        pregrant = self._choices.preauthorize(request=request)
        prepared = self._preparation.prepare(request=pregrant.request)
        return self._choices.admit(prepared=prepared, pre_evidence_grant=pregrant)
