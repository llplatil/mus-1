#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from pathlib import Path
from datetime import datetime


SECTIONS = {
    "open field": "OF",
    "open field/arean habitation": "OF",
    "novel object | familiarization session": "FAM",
    "novel object | recognition session": "NOV",
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
        "%m/%d/%Y",
        "%m/%d/%y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def parse_time_hhmm(s: str) -> tuple[int, int] | None:
    s = (s or "").strip()
    if not s:
        return None
    # keep only digits
    ds = re.sub(r"\D", "", s)
    if not ds:
        return None
    ds = ds.zfill(4)[-4:]
    try:
        hh = int(ds[:2])
        mm = int(ds[2:])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        pass
    return None


def build_ground_truth(csv_path: Path) -> dict[tuple[int, str], set[str]]:
    """Return mapping: (tag_id, section) -> set of tokens 'YYYYMMDD_HHMM'"""
    txt = csv_path.read_text(encoding="utf-8", errors="ignore")
    lines = [l.strip() for l in txt.splitlines()]
    current_section: str | None = None
    gt: dict[tuple[int, str], set[str]] = {}

    i = 0
    while i < len(lines):
        raw = lines[i]
        cols = [c.strip() for c in raw.split(",")]
        key = cols[0].strip().lower()
        # Section detection
        if key in SECTIONS:
            current_section = SECTIONS[key]
            i += 1
            # skip header row following the section line (usually)
            i += 1
            continue

        # Data rows: first col is Tag Number (int-like)
        if current_section and cols and is_int(cols[0]):
            try:
                tag = int(cols[0])
            except Exception:
                tag = None
            # Columns: Test Date ~ index 4, Time ~ index 5 (may vary case)
            if tag is not None and len(cols) >= 6:
                d = parse_date(cols[4])
                tm = parse_time_hhmm(cols[5])
                if d and tm:
                    dt = d.replace(hour=tm[0], minute=tm[1])
                    token = dt.strftime("%Y%m%d_%H%M")
                    gt.setdefault((tag, current_section), set()).add(token)
        # advance
        i += 1

    return gt


def extract_from_filename(p: Path) -> tuple[int | None, str | None, str | None]:
    """Return (tag_id, section, token 'YYYYMMDD_HHMM' or None)."""
    stem = p.stem
    parts = stem.split("_")
    if len(parts) < 4:
        return None, None, None
    # id
    tag = None
    try:
        tag = int(parts[0])
    except Exception:
        pass
    # section
    section = parts[2].upper()
    if section not in {"OF", "FAM", "NOV"}:
        section = None
    # token
    token = None
    m = re.search(r"(20\d{6})_(\d{4})", stem)
    if m:
        token = f"{m.group(1)}_{m.group(2)}"
    return tag, section, token


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: check_master_dates.py <csv_path> <file1> [file2 ...]")
        return 2
    csv_path = Path(argv[1]).expanduser()
    files = [Path(a) for a in argv[2:]]
    gt = build_ground_truth(csv_path)

    print("file,tag,section,filename_token,match,ground_truth_tokens")
    for f in files:
        tag, section, token = extract_from_filename(f)
        if tag is None or section is None or token is None:
            print(f"{f},{tag},{section},{token},INVALID,[]")
            continue
        tokens = sorted(gt.get((tag, section), []))
        match = token in tokens
        print(f"{f},{tag},{section},{token},{'OK' if match else 'MISMATCH'},{tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


