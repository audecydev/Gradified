from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
import re


FROZEN_MATRIX_SHA256 = "121F413F3C0FDE9DE2F912FE4AF300FEF8BDF6D0B46BA62B54C7AE805A9ACE2"

# Independently hard-coded manifest for frozen scoring aggregation v0.2.1.
# It is deliberately NOT derived from the test files or parsed from the matrix at runtime.
FROZEN_RED_IDS = frozenset(
    {
        "B3-AUTH-01",
        "B3-AUTH-02",
        "B3-AUTH-03",
        "B3-AUTH-04",
        "B3-AUTH-05",
        "B3-AUTH-06",
        "B3-AUTH-07",
        "B3-AUTH-08",
        "B3-AUTH-09",
        "B3-AUTH-10",
        "B3-AUTH-11",
        "B3-AUTH-12",
        "B3-AUTH-13",
        "B3-BOUND-01",
        "B3-BOUND-02",
        "B3-BOUND-03",
        "B3-BOUND-04",
        "B3-BOUND-05",
        "B3-BOUND-06",
        "B3-BOUND-07",
        "B3-FAIL-01",
        "B3-FAIL-02",
        "B3-FAIL-03",
        "B3-FAIL-04",
        "B3-FAIL-05",
        "B3-FAIL-06",
        "B3-FAIL-07",
        "B3-FAIL-08",
        "B3-FAIL-09",
        "B3-FAIL-10",
        "B3-FAIL-11",
        "B3-ID-01",
        "B3-ID-02",
        "B3-ID-03",
        "B3-ID-04",
        "B3-ID-05",
        "B3-ID-06",
        "B3-ID-07",
        "B3-ID-08",
        "B3-ID-09",
        "B3-NUM-01",
        "B3-NUM-02",
        "B3-NUM-03",
        "B3-NUM-04",
        "B3-NUM-05",
        "B3-NUM-06",
        "B3-NUM-07",
        "B3-NUM-08",
        "B3-NUM-09",
        "B3-NUM-10",
        "B3-NUM-11",
        "B3-NUM-12",
        "B3-ORDER-01",
        "B3-ORDER-02",
        "B3-ORDER-03",
        "B3-ORDER-04",
        "B3-ORDER-05",
        "B3-ORDER-06",
        "B3-PROFILE-01",
        "B3-PROFILE-02",
        "B3-PROFILE-03",
        "B3-PROFILE-04",
        "B3-PROFILE-05",
        "B3-PROV-01",
        "B3-PROV-02",
        "B3-PROV-03",
        "B3-PROV-04",
        "B3-PROV-05",
        "B3-PROV-06",
        "B3-PURE-01",
        "B3-PURE-02",
        "B3-PURE-03",
        "B3-PURE-04",
        "B3-PURE-05",
        "B3-PURE-06",
        "B3-QRES-01",
        "B3-QRES-02",
        "B3-QRES-03",
        "B3-QRES-04",
        "B3-QRES-05",
        "B3-QRES-06",
        "B3-SET-01",
        "B3-SET-02",
        "B3-SET-03",
        "B3-SET-04",
        "B3-SET-05",
        "B3-SET-06",
        "B3-SET-07",
    }
)

CONTRACT_RED_FILES = (
    "tests/contracts/test_paper_aggregation_contracts_regression.py",
    "tests/unit/test_paper_aggregation_admission_regression.py",
    "tests/unit/test_paper_aggregation_numeric_regression.py",
    "tests/unit/test_paper_aggregation_provenance_regression.py",
    "tests/property/test_paper_aggregation_regression_properties.py",
)

# Empty in v0.1: every frozen ID has exactly one executable-test mapping.
# If a future suite intentionally maps one ID to more than one test, it must name the
# exact qualified tests here; unexplained multiplicity is a traceability failure.
INTENTIONAL_MULTI_TEST_MAPPINGS: dict[str, frozenset[str]] = {}

EXACT_ID_LINE = re.compile(
    r"^B3-(?:AUTH|SET|ID|PROFILE|QRES|ORDER|NUM|BOUND|FAIL|PURE|PROV)-\d{2}$"
)


def _module_and_class_tests(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield None, node
            continue

        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        yield node.name, child


def _exact_ids_from_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    docstring = ast.get_docstring(node, clean=True)
    assert docstring is not None, f"Executable RED test {node.name} has no RED-ID docstring."

    lines = tuple(line.strip() for line in docstring.splitlines() if line.strip())
    assert lines, f"Executable RED test {node.name} has an empty RED-ID docstring."

    # No substring matching. Every non-empty line must be exactly one complete frozen-ID shape.
    for line in lines:
        assert EXACT_ID_LINE.fullmatch(line), (
            f"RED-ID docstring line {line!r} in {node.name} is not an exact ID. "
            "For multi-ID tests, place one complete B3-... ID on each line."
        )

    assert len(lines) == len(set(lines)), (
        f"Executable RED test {node.name} repeats a RED ID within its own docstring."
    )
    return lines


def _qualified_test_name(relative_path: str, class_name: str | None, function_name: str) -> str:
    stem = relative_path.replace("/", ".").removesuffix(".py")
    if class_name is None:
        return f"{stem}::{function_name}"
    return f"{stem}::{class_name}::{function_name}"


def test_red_traceability_manifest_matches_executable_contract_tests() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    id_to_tests: dict[str, set[str]] = defaultdict(set)
    executable_tests: set[str] = set()

    assert len(FROZEN_RED_IDS) == 88
    assert FROZEN_MATRIX_SHA256 == (
        "121F413F3C0FDE9DE2F912FE4AF300FEF8BDF6D0B46BA62B54C7AE805A9ACE2"
    )

    for relative_path in CONTRACT_RED_FILES:
        source_path = repo_root / relative_path
        assert source_path.is_file(), f"Missing required paper-aggregation regression test file: {relative_path}"
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

        for class_name, node in _module_and_class_tests(tree):
            qualified = _qualified_test_name(relative_path, class_name, node.name)
            assert qualified not in executable_tests, f"Duplicate executable test: {qualified}"
            executable_tests.add(qualified)

            ids = _exact_ids_from_docstring(node)
            primary_normalized = ids[0].lower().replace("-", "_")
            assert primary_normalized in node.name.lower(), (
                f"Primary RED ID {ids[0]} is not represented in test name {node.name!r}."
            )

            for red_id in ids:
                assert red_id in FROZEN_RED_IDS, (
                    f"Unknown/non-frozen RED ID {red_id} declared by {qualified}."
                )
                id_to_tests[red_id].add(qualified)

    mapped_ids = set(id_to_tests)
    missing = FROZEN_RED_IDS - mapped_ids
    unknown = mapped_ids - FROZEN_RED_IDS
    assert not missing, f"Frozen RED IDs with no executable test: {sorted(missing)}"
    assert not unknown, f"Unknown RED IDs mapped by tests: {sorted(unknown)}"

    for red_id, mapped_tests in sorted(id_to_tests.items()):
        if len(mapped_tests) <= 1:
            continue

        expected = INTENTIONAL_MULTI_TEST_MAPPINGS.get(red_id)
        assert expected is not None, (
            f"RED ID {red_id} maps to multiple tests without an explicit allow-map: "
            f"{sorted(mapped_tests)}"
        )
        assert frozenset(mapped_tests) == expected, (
            f"RED ID {red_id} multiplicity differs from the intentional allow-map. "
            f"actual={sorted(mapped_tests)}, expected={sorted(expected)}"
        )

    for red_id, expected_tests in INTENTIONAL_MULTI_TEST_MAPPINGS.items():
        assert red_id in FROZEN_RED_IDS, f"Allow-map contains unknown RED ID {red_id}."
        assert frozenset(id_to_tests.get(red_id, set())) == expected_tests

    # The frozen-ID set, not raw test-function count, is the coverage authority.
    # One test may legitimately list multiple exact IDs (one per docstring line).
    # The inverse case—one ID mapped to multiple tests—requires the explicit allow-map above.
    assert executable_tests
