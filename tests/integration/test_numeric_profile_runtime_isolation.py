from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"

_SCRIPT = r'''
from grading.contracts.errors import ScoringNumericEnvelopeError
from grading.contracts.numeric_profile import MAX_SCORING_CANONICAL_DIGITS
from grading.contracts.policy import RoundingMode, RoundingRule
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import exact_sum
from grading.scoring.rounding import _round_to_increment

N = MAX_SCORING_CANONICAL_DIGITS
x = ScoringDecimal.from_raw("9" * N)
y = ScoringDecimal.from_raw("1e-4095")
negative_x = ScoringDecimal.from_raw("-" + ("9" * N))

# Successful path materializes >4300-digit integer intermediates but returns y.
result = exact_sum((x, y, negative_x))
assert result == y

# Same exact out-of-profile result must always fail with the profile error.
try:
    exact_sum((x, y))
except ScoringNumericEnvelopeError:
    pass
else:
    raise AssertionError("out-of-envelope sum did not fail")

# Rounding produces an >4300-digit selected multiple and returns an in-profile x.
rule = RoundingRule(
    "ROUND-1",
    ScoringDecimal.from_raw("1e-4095"),
    RoundingMode.HALF_UP,
)
rounded = _round_to_increment(x, rule)
assert rounded == x

# Large exact integer construction must also be independent of int-string policy.
integer_limit_minus_one = (10 ** N) - 1
integer_value = ScoringDecimal.from_raw(integer_limit_minus_one)
assert integer_value == x

print("PROFILE_V1_OK")
'''


@pytest.mark.parametrize("int_string_limit", ["4300", "640", "0"])
def test_python_int_string_limit_cannot_change_numeric_profile_behavior(
    int_string_limit: str,
) -> None:
    env = os.environ.copy()
    env["PYTHONINTMAXSTRDIGITS"] = int_string_limit
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(SRC)
        if not existing_pythonpath
        else os.pathsep.join((str(SRC), existing_pythonpath))
    )

    completed = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, (
        f"subprocess failed under PYTHONINTMAXSTRDIGITS={int_string_limit}; "
        f"stderr={completed.stderr[-2000:]}"
    )
    assert completed.stdout.strip() == "PROFILE_V1_OK"
