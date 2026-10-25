# Benchmark qualification

The benchmark package supports offline, source-bound evaluation against teacher-labelled examples. It does not grant permission to publish grades and does not substitute for real academic-quality measurement.

`benchmark/qualification.py` admits bounded benchmark source descriptions; `benchmark/label_reference.py` and `benchmark/label_custody.py` associate teacher reference evidence with a fixed case. `benchmark/offline_trial.py`, `benchmark/source_bound_trial.py` and `benchmark/recovery.py` handle nonpublishing replay and recovery.

## Academic acceptance work

Collect genuine representative school papers, the exact rubric version, source scans, admitted OCR evidence, an independent teacher mark and the installed model/runtime revision. Compare question-level criteria and final marks, record false positives, false negatives and uncertainty, and review disagreements with subject specialists.

A synthetic fixture validates deterministic plumbing but cannot establish an accurate review-confidence threshold, general diagram understanding or correct grading of arbitrary derivations. Never describe a passing offline unit test as proof of a production school's grading accuracy.

See [Capabilities](capabilities_and_limitations.md) and [Integration tests](integration_test_plan.md).
