"""Shared QC-flag utilities for NOR/NOF and EZM experiment JSONs.

Provides a unified schema for ``qc_flags`` blocks stored in each experiment
JSON, plus helpers to read, write, compute auto-flags, and maintain an
append-only audit history.

Schema (``qc_flags`` key inside each experiment JSON)::

    {
        "status": "not_reviewed" | "good" | "poor_tracking" | "exclude" | "needs_review",
        "auto_flags": ["LOW_TRACKING", ...],
        "flags": {
            "pairing": { ... },
            "arena":   { ... },
            "tracking": { ... }
        },
        "notes": "",
        "history": [
            {"action": "...", "at": "...", "by": "...", "detail": "..."},
            ...
        ]
    }
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Status vocabulary ────────────────────────────────────────────────────────

VALID_STATUSES = (
    "not_reviewed",
    "good",
    "poor_tracking",
    "exclude",
    "needs_review",
)

# ── Flag vocabulary ──────────────────────────────────────────────────────────
#
# Two layers, with different semantics:
#
#   1. TRACKING_QUALITY_FLAGS  — task-agnostic, derived from the DLC
#      predictions CSV alone. Computed by
#      ``mus1.compute.tracking_confidence``. These flags say whether the
#      experiment is *worth* deeper task-specific QC at all (the
#      "don't try to polish garbage" gate). Canonical home is
#      ``mus1.compute.tracking_flags``; re-exported here for back-compat.
#
#   2. NOR_NOF_FLAG_VOCABULARY / EZM auto-flags — task-specific, derived
#      from computed metrics (zone classification, interaction zones,
#      …). Meaningful only after the relevant batch_run / exploratory_run
#      exists.
#
# Both layers can coexist in ``qc_flags.auto_flags[]``. UI panes display
# tracking-quality flags first because they gate the rest.

# Canonical universal-layer vocabulary lives in compute.tracking_flags.
# Re-export for callers still importing from this module.
from ..compute.tracking_flags import (  # noqa: E402  (after stdlib block above)
    TRACKING_QUALITY_FLAGS,
    merge_into_qc_flags as merge_tracking_confidence_into_qc_flags,
)

NOR_NOF_FLAG_VOCABULARY = [
    "LOW_TRACKING",
    "HIGH_CORRECTION_RATE",
    "BODYPART_DISAGREEMENT",
    "POOR_ARENA_FIT",
    "ZERO_INTERACTION",
    "ARENA_FIT_OUTLIER",
    "OBJECT_CENTER_OUTLIER",
    "novel_side_unknown",
]


# ── Read / bootstrap ────────────────────────────────────────────────────────

def read_qc_flags(data: dict) -> dict:
    """Return the ``qc_flags`` block from an experiment dict, creating a
    skeleton if absent.  Never mutates *data* — returns a fresh dict when
    the key is missing.
    """
    qf = data.get("qc_flags")
    if isinstance(qf, dict):
        return qf
    return _empty_qc_flags()


def _empty_qc_flags() -> dict:
    return {
        "status": "not_reviewed",
        "auto_flags": [],
        "flags": {
            "pairing": {},
            "arena": {},
            "tracking": {},
        },
        "notes": "",
        "history": [],
    }


# ── Write helpers ────────────────────────────────────────────────────────────

def set_status(
    qf: dict,
    new_status: str,
    by: str = "app",
    detail: str = "",
) -> None:
    """Set the human-review status and append to history."""
    if new_status not in VALID_STATUSES:
        raise ValueError("Invalid status %r; expected one of %s" % (new_status, VALID_STATUSES))
    old = qf.get("status", "not_reviewed")
    qf["status"] = new_status
    _append_history(qf, "status_change", by, "%s -> %s%s" % (old, new_status, (": " + detail) if detail else ""))


def set_auto_flags(qf: dict, flags: List[str], by: str = "auto") -> None:
    """Replace the auto_flags list and log the change."""
    old = sorted(qf.get("auto_flags") or [])
    new = sorted(set(flags))
    qf["auto_flags"] = new
    if old != new:
        _append_history(qf, "auto_flags_update", by, "flags=%s" % ",".join(new) if new else "flags=[]")


def set_notes(qf: dict, notes: str, by: str = "app") -> None:
    """Update free-text notes."""
    qf["notes"] = notes


def _append_history(qf: dict, action: str, by: str, detail: str) -> None:
    hist = qf.setdefault("history", [])
    hist.append({
        "action": action,
        "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "by": by,
        "detail": detail,
    })


# ── Auto-flag computation (NOR/NOF) ─────────────────────────────────────────

def compute_nor_nof_auto_flags(data: dict) -> List[str]:
    """Derive auto-flags from an experiment JSON's existing fields.

    This inspects:
    - ``metadata.experiment_level.novel_side``
    - ``nor_nof_pair``
    - ``arena_markings``
    - ``dlc`` / tracking quality metrics (when available)
    - ``computed_metrics`` (when available)

    Returns a sorted, deduplicated list of flag strings.
    """
    flags: List[str] = []
    md = data.get("metadata", {})
    el = md.get("experiment_level", {})
    exp_type = data.get("experiment_type", "")

    # novel_side_unknown — NOR only (NOF familiarization has two identical objects)
    if exp_type == "NOR":
        ns = el.get("novel_side")
        if not ns or str(ns).lower() in ("", "none", "null", "unknown"):
            flags.append("novel_side_unknown")

    # pairing check
    pair = data.get("nor_nof_pair")
    if not isinstance(pair, dict) or not pair.get("paired_experiment_id"):
        # Missing pairing — informational, not necessarily exclusion-worthy
        pass

    # arena fit quality (if arena_markings present)
    am = data.get("arena_markings", {})
    nor_nof_marks = am.get("nor_nof_arena") or am.get("arena_boundary") or {}
    if nor_nof_marks:
        fit_quality = nor_nof_marks.get("fit_quality")
        if fit_quality is not None and float(fit_quality) < 0.8:
            flags.append("POOR_ARENA_FIT")

    # tracking quality from DLC (if summary stats exist)
    dlc = data.get("dlc", {})
    tracking_summary = dlc.get("tracking_summary", {})
    frac_below = tracking_summary.get("frac_frames_below_threshold")
    if frac_below is not None and float(frac_below) > 0.30:
        flags.append("LOW_TRACKING")

    # computed_metrics — object interaction
    cm = data.get("computed_metrics", {})
    nor_nof_metrics = cm.get("nor_nof_interaction", {})
    total_interaction = nor_nof_metrics.get("total_interaction_time")
    if total_interaction is not None and float(total_interaction) == 0.0:
        flags.append("ZERO_INTERACTION")

    return sorted(set(flags))


# ── JSON persistence ────────────────────────────────────────────────────────

def save_qc_flags_to_json(json_path: Path, qf: dict, provenance_key: str = "_qc_flags_init") -> None:
    """Read *json_path*, set ``qc_flags`` to *qf*, add provenance, and write back."""
    data = json.loads(json_path.read_text())
    data["qc_flags"] = qf
    if provenance_key:
        data[provenance_key] = {
            "action": "qc_flags populated",
            "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "by": "qc_flags_shared.save_qc_flags_to_json",
        }
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n")
