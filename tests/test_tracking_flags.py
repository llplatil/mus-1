"""Tests for ``mus1.compute.tracking_flags`` — vocabulary + merger."""
from __future__ import annotations

from mus1.compute.tracking_flags import (
    TRACKING_QUALITY_FLAGS,
    merge_into_qc_flags,
)


def test_vocabulary_is_stable():
    """Names are part of the JSON contract; locking them prevents typos."""
    assert TRACKING_QUALITY_FLAGS == [
        "LOW_LIKELIHOOD_OVERALL",
        "BODYPART_FAILURE",
        "LIKELIHOOD_DROPOUT_RUN",
    ]


def test_merge_into_empty_qc_flags():
    out = merge_into_qc_flags(
        None,
        {"flags": ["LOW_LIKELIHOOD_OVERALL"]},
    )
    assert out["auto_flags"] == ["LOW_LIKELIHOOD_OVERALL"]
    assert out["status"] == "not_reviewed"
    assert out["history"] == []


def test_merge_preserves_task_specific_flags():
    """Existing non-universal flags must survive the merge."""
    qf = {
        "status": "good",
        "auto_flags": ["POSSIBLE_INVERSION", "HIGH_OFF_TRACK"],
        "flags": {"tracking": {}},
        "notes": "",
        "history": [],
    }
    tc = {"flags": ["LOW_LIKELIHOOD_OVERALL"]}
    out = merge_into_qc_flags(qf, tc)
    assert "POSSIBLE_INVERSION" in out["auto_flags"]
    assert "HIGH_OFF_TRACK" in out["auto_flags"]
    assert "LOW_LIKELIHOOD_OVERALL" in out["auto_flags"]


def test_merge_strips_stale_universal_flags():
    """Re-running with cleaner data must remove flags that no longer apply."""
    qf = {
        "auto_flags": ["LOW_LIKELIHOOD_OVERALL", "BODYPART_FAILURE",
                       "POSSIBLE_INVERSION"],
    }
    # New tracking_confidence run: only one flag remains
    tc = {"flags": ["BODYPART_FAILURE"]}
    out = merge_into_qc_flags(qf, tc)
    assert "LOW_LIKELIHOOD_OVERALL" not in out["auto_flags"]
    assert "BODYPART_FAILURE" in out["auto_flags"]
    # Task-specific flag is preserved
    assert "POSSIBLE_INVERSION" in out["auto_flags"]


def test_merge_with_no_tc_clears_universal_layer():
    """If tracking_confidence is absent, universal flags drop out."""
    qf = {
        "auto_flags": ["LOW_LIKELIHOOD_OVERALL", "POSSIBLE_INVERSION"],
    }
    out = merge_into_qc_flags(qf, None)
    assert "LOW_LIKELIHOOD_OVERALL" not in out["auto_flags"]
    assert "POSSIBLE_INVERSION" in out["auto_flags"]


def test_merge_is_idempotent():
    qf = {"auto_flags": ["POSSIBLE_INVERSION"]}
    tc = {"flags": ["LOW_LIKELIHOOD_OVERALL"]}
    out1 = merge_into_qc_flags(qf, tc)
    out2 = merge_into_qc_flags(out1, tc)
    assert out1["auto_flags"] == out2["auto_flags"]


def test_merge_does_not_mutate_input():
    qf = {"auto_flags": ["POSSIBLE_INVERSION"]}
    original = list(qf["auto_flags"])
    merge_into_qc_flags(qf, {"flags": ["LOW_LIKELIHOOD_OVERALL"]})
    assert qf["auto_flags"] == original


def test_merge_ignores_unknown_flags_in_tc():
    """If tracking_confidence emits a flag not in our vocabulary,
    we don't blindly add it — only the documented universal layer goes through."""
    qf = {"auto_flags": []}
    out = merge_into_qc_flags(qf, {"flags": ["LOW_LIKELIHOOD_OVERALL", "NOT_A_REAL_FLAG"]})
    assert out["auto_flags"] == ["LOW_LIKELIHOOD_OVERALL"]
