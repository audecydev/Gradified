from enum import Enum


def test_context_policy_is_exact_closed_authorized_vocabulary() -> None:
    # Import inside the test so RED3a is one causal test failure rather than a
    # collection error when the executable vocabulary does not yet exist.
    from grading.active_question_authority import ContextPolicy

    assert issubclass(ContextPolicy, str)
    assert issubclass(ContextPolicy, Enum)

    expected = {
        "DIRECT": "DIRECT",
        "DIRECT_PLUS_REFERENCE": "DIRECT_PLUS_REFERENCE",
        "HYBRID_RETRIEVAL": "HYBRID_RETRIEVAL",
        "REFERENCE_ONLY": "REFERENCE_ONLY",
    }

    # __members__ includes aliases. Comparing the complete name->value mapping
    # proves a closed vocabulary without inventing declaration-order semantics.
    actual = {
        name: member.value
        for name, member in ContextPolicy.__members__.items()
    }
    assert actual == expected
    assert all(
        type(member.value) is str
        for member in ContextPolicy.__members__.values()
    )
