"""Read/write per-experiment DLC tracking-comparison verdicts.

Verdicts live under ``extraction.tracking_comparisons[]`` in the experiment
JSON — a peer of ``dlc_runs[]``, NOT under ``qc_flags`` (which is a single
status string per experiment). Each verdict is keyed by the *unordered* pair
of run_ids, so ``(v1, v2)`` and ``(v2, v1)`` collapse to one row; re-review
of the same pair overwrites in place.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_VERDICTS = ("A_better", "B_better", "tie", "both_bad", "not_reviewed")


def _norm_pair(run_a_id: str, run_b_id: str) -> Tuple[str, str]:
    """Return the run-id pair in a canonical (sorted) order."""
    return tuple(sorted((run_a_id, run_b_id)))  # type: ignore[return-value]


def list_comparisons(extraction: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(extraction, dict):
        return []
    out = extraction.get("tracking_comparisons")
    return out if isinstance(out, list) else []


def read_comparison(
    extraction: Optional[Dict[str, Any]], run_a_id: str, run_b_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the stored verdict for a run pair (order-agnostic), or None."""
    key = _norm_pair(run_a_id, run_b_id)
    for entry in list_comparisons(extraction):
        if _norm_pair(entry.get("run_a_id", ""), entry.get("run_b_id", "")) == key:
            return entry
    return None


def write_comparison(
    json_path: Path,
    *,
    run_a_id: str,
    run_b_id: str,
    verdict: str,
    notes: str = "",
    metrics_snapshot: Optional[Dict[str, Any]] = None,
    reviewed_by: str = "app",
) -> Dict[str, Any]:
    """Upsert a comparison verdict into the experiment JSON (atomic write).

    The pair is stored in canonical sorted order; an existing verdict for
    the same pair is replaced. Returns the stored entry.
    """
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"invalid verdict {verdict!r}; expected one of {VALID_VERDICTS}")

    lo, hi = _norm_pair(run_a_id, run_b_id)
    data = json.loads(json_path.read_text())
    ext = data.setdefault("extraction", {})
    comps = ext.setdefault("tracking_comparisons", [])

    entry = {
        "run_a_id": lo,
        "run_b_id": hi,
        "verdict": verdict,
        "notes": notes.strip(),
        "metrics_snapshot": metrics_snapshot or {},
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewed_by,
    }

    replaced = False
    for i, e in enumerate(comps):
        if _norm_pair(e.get("run_a_id", ""), e.get("run_b_id", "")) == (lo, hi):
            comps[i] = entry
            replaced = True
            break
    if not replaced:
        comps.append(entry)

    tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, json_path)
    return entry
