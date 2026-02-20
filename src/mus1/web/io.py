from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_meta(meta_json: Optional[str]) -> Dict[str, Any]:
    if not meta_json:
        return {}
    try:
        return json.loads(meta_json)
    except Exception:
        return {"_raw": meta_json}


def read_csv_rows(path: Path, *, limit: int = 500) -> List[Dict[str, Any]]:
    """
    Small CSV reader for UI tables (keeps deps minimal).
    """
    out: List[Dict[str, Any]] = []
    with path.open() as f:
        r = csv.DictReader(f)
        for i, row in enumerate(r):
            if i >= int(limit):
                break
            out.append({k: row.get(k) for k in (row.keys() or [])})
    return out

