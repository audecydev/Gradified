from __future__ import annotations

from dataclasses import fields
from decimal import (
    Clamped,
    Context,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_FLOOR,
    Rounded,
    Subnormal,
    Underflow,
)
from fractions import Fraction
from importlib import import_module
from types import SimpleNamespace

import pytest

from grading.contracts.errors import (
    InvalidScoringAuthorityError,
    ScoreOutOfRangeError,
    ScoringNumericEnvelopeError,
)
from grading.contracts.numeric_profile import (
    MAX_SCORING_CANONICAL_DIGITS,
    NUMERIC_PROFILE_VERSION,
)
from grading.contracts.result import (
    CriterionEffect,
    QuestionScoreResult,
    RubricRef,
    RuleDecision,
    RuleType,
    ScoreStage,
    ScoreStageEffect,
    ScoringPolicyRef,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import exact_sum


FROZEN_MATRIX_SHA256 = "121F413F3C0FDE9DE2F912FE4AF300FEF8BDF6D0B46BA62B54C7AE805A9ACE2"


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def _required_module(name: str):
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            pytest.fail(
                f"EXPECTED_CONTRACT_ABSENCE: required B3 module {name!r} is absent.",
                pytrace=False,
            )
        raise


def _required_symbol(module: object, module_name: str, symbol: str):
    value = getattr(module, symbol, None)
    if value is None:
        pytest.fail(
            f"EXPECTED_CONTRACT_ABSENCE: {module_name}.{symbol} is absent.",
            pytrace=False,
        )
    return value


def load_b3() -> SimpleNamespace:
    contracts_name = "grading.contracts.paper_aggregation"
    result_name = "grading.contracts.result"
    errors_name = "grading.contracts.errors"
    scoring_name = "grading.scoring.paper_aggregation"

    contracts = _required_module(contracts_name)
    result_module = _required_module(result_name)
    errors = _required_module(errors_name)
    scoring = _required_module(scoring_name)

    surface = SimpleNamespace(
        contracts_module=contracts,
        result_module=result_module,
        errors_module=errors,
        paper_module=scoring,
        GradingSpecRef=_required_symbol(contracts, contracts_name, "GradingSpecRef"),
        ExpectedQuestionResult=_required_symbol(
            contracts,
            contracts_name,
            "ExpectedQuestionResult",
        ),
        ResolvedPaperScoringAuthority=_required_symbol(
            contracts,
            contracts_name,
            "ResolvedPaperScoringAuthority",
        ),
        PaperScoreResult=_required_symbol(result_module, result_name, "PaperScoreResult"),
        InvalidPaperAggregationInputError=_required_symbol(
            errors,
            errors_name,
            "InvalidPaperAggregationInputError",
        ),
        aggregate_paper=_required_symbol(scoring, scoring_name, "aggregate_paper"),
    )
    assert callable(surface.aggregate_paper), (
        "EXPECTED_CONTRACT_ABSENCE: grading.scoring.paper_aggregation.aggregate_paper "
        "must be callable."
    )
    return surface


def rubric_ref(
    *,
    rubric_id: str = "rubric",
    version: int = 1,
) -> RubricRef:
    return RubricRef(rubric_id, version)


def policy_ref(
    *,
    policy_id: str = "policy",
    version: int = 1,
    semantics: str = "1",
) -> ScoringPolicyRef:
    return ScoringPolicyRef(policy_id, version, semantics)


def expected_question(
    b3: SimpleNamespace,
    question_id: str,
    *,
    rubric: RubricRef | None = None,
    policy: ScoringPolicyRef | None = None,
):
    return b3.ExpectedQuestionResult(
        question_id=question_id,
        rubric_ref=rubric or rubric_ref(rubric_id=f"rubric-{question_id}"),
        scoring_policy_ref=policy or policy_ref(policy_id=f"policy-{question_id}"),
    )


def grading_spec_ref(
    b3: SimpleNamespace,
    *,
    spec_id: str = "grading-spec",
    version: int = 1,
):
    return b3.GradingSpecRef(id=spec_id, version=version)


def authority(
    b3: SimpleNamespace,
    expected: tuple[object, ...],
    *,
    spec_id: str = "grading-spec",
    spec_version: int = 1,
    minimum: object = "0",
    maximum: object = "20",
):
    return b3.ResolvedPaperScoringAuthority(
        grading_spec_ref=grading_spec_ref(
            b3,
            spec_id=spec_id,
            version=spec_version,
        ),
        expected_questions=expected,
        minimum_score=minimum if type(minimum) is ScoringDecimal else sd(minimum),
        maximum_score=maximum if type(maximum) is ScoringDecimal else sd(maximum),
    )


def question_result(
    question_id: str,
    *,
    final: object = "1",
    minimum: object = "0",
    maximum: object = "10",
    rubric: RubricRef | None = None,
    policy: ScoringPolicyRef | None = None,
    profile: str = NUMERIC_PROFILE_VERSION,
    criterion_effects: tuple[CriterionEffect, ...] = (),
    rule_decisions: tuple[RuleDecision, ...] = (),
    stage_effects: tuple[ScoreStageEffect, ...] = (),
    base_subtotal: object | None = None,
    score_before_rounding: object | None = None,
) -> QuestionScoreResult:
    final_value = final if type(final) is ScoringDecimal else sd(final)
    base_value = (
        final_value
        if base_subtotal is None
        else base_subtotal
        if type(base_subtotal) is ScoringDecimal
        else sd(base_subtotal)
    )
    before_value = (
        final_value
        if score_before_rounding is None
        else score_before_rounding
        if type(score_before_rounding) is ScoringDecimal
        else sd(score_before_rounding)
    )

    return QuestionScoreResult(
        question_id=question_id,
        rubric_ref=rubric or rubric_ref(rubric_id=f"rubric-{question_id}"),
        scoring_policy_ref=policy or policy_ref(policy_id=f"policy-{question_id}"),
        numeric_profile_version=profile,
        criterion_effects=criterion_effects,
        rule_decisions=rule_decisions,
        stage_effects=stage_effects,
        base_subtotal=base_value,
        score_before_rounding=before_value,
        final_score=final_value,
        minimum_score=minimum if type(minimum) is ScoringDecimal else sd(minimum),
        maximum_score=maximum if type(maximum) is ScoringDecimal else sd(maximum),
    )


def valid_pair(
    b3: SimpleNamespace,
    question_id: str,
    *,
    final: object = "1",
    minimum: object = "0",
    maximum: object = "10",
    rubric_id: str | None = None,
    rubric_version: int = 1,
    policy_id: str | None = None,
    policy_version: int = 1,
    semantics: str = "1",
    profile: str = "1",
):
    rr = rubric_ref(
        rubric_id=rubric_id or f"rubric-{question_id}",
        version=rubric_version,
    )
    pr = policy_ref(
        policy_id=policy_id or f"policy-{question_id}",
        version=policy_version,
        semantics=semantics,
    )
    return (
        expected_question(b3, question_id, rubric=rr, policy=pr),
        question_result(
            question_id,
            final=final,
            minimum=minimum,
            maximum=maximum,
            rubric=rr,
            policy=pr,
            profile=profile,
        ),
    )


def paper_fixture(
    b3: SimpleNamespace,
    rows: tuple[tuple[str, object, object, object], ...],
    *,
    paper_minimum: object = "0",
    paper_maximum: object = "20",
    spec_id: str = "grading-spec",
    spec_version: int = 1,
):
    pairs = tuple(
        valid_pair(
            b3,
            question_id,
            final=final,
            minimum=minimum,
            maximum=maximum,
        )
        for question_id, final, minimum, maximum in rows
    )
    expected = tuple(pair[0] for pair in pairs)
    results = tuple(pair[1] for pair in pairs)
    return (
        authority(
            b3,
            expected,
            spec_id=spec_id,
            spec_version=spec_version,
            minimum=paper_minimum,
            maximum=paper_maximum,
        ),
        results,
    )


def assert_invalid_input(b3: SimpleNamespace, callable_obj, *args, **kwargs):
    with pytest.raises(b3.InvalidPaperAggregationInputError) as captured:
        callable_obj(*args, **kwargs)
    return captured


def fraction_from_sd(value: ScoringDecimal) -> Fraction:
    sign, digits, exponent = value.as_decimal().as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = (coefficient * 10) + digit
    if sign:
        coefficient = -coefficient
    if exponent >= 0:
        return Fraction(coefficient * (10**exponent), 1)
    return Fraction(coefficient, 10 ** (-exponent))


def hostile_context() -> Context:
    context = Context(
        prec=1,
        rounding=ROUND_FLOOR,
        Emin=-1,
        Emax=1,
        capitals=0,
        clamp=1,
    )
    for signal in (
        Clamped,
        DivisionByZero,
        Inexact,
        InvalidOperation,
        Overflow,
        Rounded,
        Subnormal,
        Underflow,
    ):
        context.traps[signal] = True
        context.flags[signal] = False
    return context


def context_snapshot(context: Context) -> tuple[object, ...]:
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        tuple(
            sorted(
                (signal.__name__, enabled)
                for signal, enabled in context.traps.items()
            )
        ),
        tuple(
            sorted(
                (signal.__name__, enabled)
                for signal, enabled in context.flags.items()
            )
        ),
    )


def weird_b2_provenance() -> tuple[
    tuple[CriterionEffect, ...],
    tuple[RuleDecision, ...],
    tuple[ScoreStageEffect, ...],
]:
    return (
        (
            CriterionEffect(
                criterion_id="C-WEIRD",
                selected_level="L-WEIRD",
                base_contribution=sd("9"),
                effective_contribution=sd("-7"),
                blocking_dependency_rule_ids=("NOT-A-REAL-CHAIN",),
            ),
        ),
        (
            RuleDecision(
                rule_id="R-WEIRD",
                rule_type=RuleType.CAP,
                triggered=True,
                configured_effect=sd("3"),
            ),
        ),
        (
            ScoreStageEffect(
                stage=ScoreStage.ROUNDING,
                before=sd("999"),
                after=sd("-999"),
                source_rule_ids=("R-WEIRD",),
            ),
        ),
    )


def result_field_names(result_type: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(result_type))


def authority_field_names(authority_type: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(authority_type))
