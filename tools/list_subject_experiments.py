#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from pathlib import Path
from datetime import datetime


SECTION_TO_TYPE = {
    "open field/arean habitation": "OF",
    "novel object | familiarization session": "FAM",
    "novel object | recognition session": "NOV",
    "elevated zero maze": "EZM",
    "rota rod": "RR",
}


def is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except Exception:
        return False


def parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    fmts = [
        "%m/%d/%Y",
        "%m/%d/%y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def extract_records(csv_path: Path) -> list[tuple[int, str, str]]:
    """Return list of (subject_id, exp_type, date_yyyy_mm_dd)."""
    txt = csv_path.read_text(encoding="utf-8", errors="ignore")
    lines = [l.strip() for l in txt.splitlines()]
    current_section: str | None = None
    out: list[tuple[int, str, str]] = []

    i = 0
    while i < len(lines):
        raw = lines[i]
        cols = [c.strip() for c in raw.split(",")]
        key = cols[0].strip().lower()
        # Section detection
        if key in SECTION_TO_TYPE:
            current_section = SECTION_TO_TYPE[key]
            i += 1
            # Skip header line following section if present
            i += 1
            continue

        if current_section and cols and is_int(cols[0]):
            try:
                tag = int(cols[0])
            except Exception:
                tag = None
            # Test Date typically in column index 4
            if tag is not None and len(cols) >= 5:
                d = parse_date(cols[4])
                if d:
                    out.append((tag, current_section, d.strftime("%Y-%m-%d")))
        i += 1

    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: list_subject_experiments.py <csv1> [csv2 ...]")
        return 2
    records: list[tuple[int, str, str]] = []
    for a in argv[1:]:
        csv_path = Path(a).expanduser()
        if csv_path.exists():
            records.extend(extract_records(csv_path))

    # Sort by subject_id then date then exp_type
    records.sort(key=lambda r: (r[0], r[2], r[1]))

    print("subject_id,experiment_type,date")
    for sid, et, dt in records:
        print(f"{sid},{et},{dt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


