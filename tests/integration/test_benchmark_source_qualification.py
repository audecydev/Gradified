from dataclasses import replace
import pytest

from grading.benchmark.qualification import (
    BenchmarkCaseReference, BenchmarkSourceManifest, BenchmarkSourceDenied,
    admit_benchmark_source_shape,
)


def case(number):
    return BenchmarkCaseReference(f'case-{number}', f'teacher-label-{number}',
                                  'rev-1', f'{number:064x}')


def source():
    return BenchmarkSourceManifest('tenant-A', 'run-A', 'source-policy', 'v1',
        'dataset-A', 'rev-1', 'a'*64, 'evaluator-A', 'config-A',
        (case(1),), (case(2),), (case(3),))


def accept(s):
    return admit_benchmark_source_shape(source=s,
                       max_identifier_characters=120, max_cases=12)


def test_admitted_is_structural_not_teacher_or_execution_authority():
    result = accept(source())
    assert result.evidence_type == 'STRUCTURAL_BENCHMARK_SOURCE_UNVERIFIED'
    assert result.manifest.heldout[0].case_ref == 'case-3'


@pytest.mark.parametrize('modify', [
    lambda x: replace(x, heldout=(x.development[0],)),
    lambda x: replace(x, heldout=(replace(case(3), teacher_annotation_ref='teacher-label-1'),)),
    lambda x: replace(x, heldout=(replace(case(3), teacher_annotation_sha256='bad'),)),
    lambda x: replace(x, heldout=[case(3)]),
    lambda x: replace(x, development=()),
    lambda x: replace(x, dataset_sha256='b'*63),
    lambda x: replace(x, configuration_ref=' bad'),
    lambda x: replace(x, heldout=(case(3),)*15),
    lambda x: replace(x, heldout=(replace(case(3), case_ref=True),)),
])
def test_invalid_benchmark_source_denied(modify):
    with pytest.raises(BenchmarkSourceDenied):
        accept(modify(source()))


def test_original_manifest_mutation_cannot_change_detached_admission():
    value = source()
    admitted = accept(value)
    object.__setattr__(value, 'heldout', (case(444),))
    assert admitted.manifest.heldout[0].case_ref == 'case-3'


def test_no_unbounded_source_shape_or_bool_limits():
    with pytest.raises(BenchmarkSourceDenied):
        admit_benchmark_source_shape(source=source(), max_identifier_characters=True, max_cases=12)
    with pytest.raises(BenchmarkSourceDenied):
        admit_benchmark_source_shape(source=source(), max_identifier_characters=100, max_cases=True)


def test_shared_teacher_label_different_revision_still_rejected():
    value = source()
    swapped = replace(value, heldout=(replace(case(3),teacher_annotation_ref='teacher-label-1',
                                              teacher_annotation_revision='rev-2'),))
    with pytest.raises(BenchmarkSourceDenied):
        accept(swapped)


def test_benchmark_source_public_failure_strips_ambient_exception_context():
    try:
        raise RuntimeError('PRIVATE source reference')
    except RuntimeError:
        with pytest.raises(BenchmarkSourceDenied) as captured:
            accept(replace(source(), dataset_sha256='not a digest'))
    assert captured.value.__context__ is None and captured.value.__cause__ is None
