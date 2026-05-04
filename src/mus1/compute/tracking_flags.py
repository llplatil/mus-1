"""Universal tracking-quality flag vocabulary + the single merger helper.

Two responsibilities, deliberately small:

1. **Vocabulary** — the canonical list of task-agnostic tracking
   quality flags emitted by ``mus1.compute.tracking_confidence``. Held
   here (not in ``web/qc_flags_shared``) so non-web callers — CLI,
   FastAPI, Slurm batch wrappers — can import without pulling Streamlit
   into the dependency tree.

2. **Merger** — :func:`merge_into_qc_flags`. Copies tracking-confidence
   flags into the experiment JSON's ``qc_flags.auto_flags`` list while
   preserving any task-specific auto-flags already present. Called by
   *both* the CLI ``--write`` path and the QC pane's Compute button —
   single source of truth, no divergence.

The companion ``web/qc_flags_shared.py`` re-exports
``TRACKING_QUALITY_FLAGS`` for back-compat with existing imports.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


#: Universal tracking-quality flag vocabulary. Exact strings emitted
#: by ``mus1.compute.tracking_confidence.compute_tracking_confidence``.
TRACKING_QUALITY_FLAGS: List[str] = [
    "LOW_LIKELIHOOD_OVERALL",
    "BODYPART_FAILURE",
    "LIKELIHOOD_DROPOUT_RUN",
]


def merge_into_qc_flags(
    qf: Optional[Dict[str, Any]],
    tracking_confidence: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge tracking-confidence flags into ``qc_flags.auto_flags``.

    Returns a fresh ``qf`` dict (does not mutate the input). Preserves
    every existing entry of ``qf.auto_flags`` that is *not* in
    :data:`TRACKING_QUALITY_FLAGS` (i.e. task-specific flags survive),
    then adds whatever the latest tracking-confidence run produced.

    Idempotent: calling twice with the same inputs yields the same
    output. Re-running tracking-confidence with different thresholds
    correctly removes flags that no longer apply.

    Parameters
    ----------
    qf : the current ``qc_flags`` block from the experiment JSON. May
        be ``None`` or an empty dict; a skeleton is built if absent.
    tracking_confidence : the ``extraction.tracking_confidence`` block
        produced by ``compute_tracking_confidence``. May be ``None``;
        in that case all tracking-quality flags are removed from
        ``auto_flags`` (universal layer is empty when no run exists).

    Returns
    -------
    dict — the new ``qc_flags`` block to persist.
    """
    out = dict(qf) if isinstance(qf, dict) else {}
    out.setdefault("status", "not_reviewed")
    out.setdefault("flags", {})
    out.setdefault("notes", "")
    out.setdefault("history", [])

    existing = list(out.get("auto_flags") or [])
    # Strip prior universal-layer flags; keep task-specific ones untouched.
    preserved = [f for f in existing if f not in TRACKING_QUALITY_FLAGS]

    new_universal: List[str] = []
    if isinstance(tracking_confidence, dict):
        new_universal = [
            f for f in (tracking_confidence.get("flags") or [])
            if f in TRACKING_QUALITY_FLAGS
        ]

    out["auto_flags"] = preserved + new_universal
    return out
