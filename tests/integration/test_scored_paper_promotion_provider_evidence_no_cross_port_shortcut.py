"""governed scored-paper handoff requires original attempt accounting one-operation facts to agree with physical provider inventory multioperation facts."""
from grading.integration.scored_paper_promotion import _compatible_provider_evidence
from grading.integration.paper_accounting import PaperAccountingState as A
from grading.integration.paper_provider_inventory import ProviderInventoryState as I


def test_native_no_transport_requires_both_sources_not_applicable():
    assert _compatible_provider_evidence(True,A.NOT_APPLICABLE,I.NOT_APPLICABLE)
    assert not _compatible_provider_evidence(True,A.NOT_APPLICABLE,I.COMPLETENESS_REPORTED)
    assert not _compatible_provider_evidence(True,A.REPORTED_RECORDED,I.NOT_APPLICABLE)


def test_real_provider_transport_never_inherits_c4d_no_transport():
    assert not _compatible_provider_evidence(False,A.NOT_APPLICABLE,I.COMPLETENESS_REPORTED)
    assert _compatible_provider_evidence(False,A.REPORTED_RECORDED,I.MEASUREMENTS_REPORTED)
    assert _compatible_provider_evidence(False,A.NOT_APPLICABLE,I.NOT_APPLICABLE)
    assert not _compatible_provider_evidence(False,A.REPORTED_RECORDED,I.NOT_APPLICABLE)
    assert not _compatible_provider_evidence(False,A.REPORTED_RECORDED,I.EVENTS_RECORDED)
