from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional, Set
import re


# ------------------------------
# Subject/experiment CSV parsing
# ------------------------------

SECTION_TO_TYPE = {
    "open field/arean habitation": "OF",
    "novel object | familiarization session": "FAM",
    "novel object | recognition session": "NOV",
    "elevated zero maze": "EZM",
    "rota rod": "RR",
}


def _is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except Exception:
        return False


def _parse_date_mdY(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    fmts = ["%m/%d/%Y", "%m/%d/%y"]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def extract_subject_experiment_records(csv_path: Path) -> List[Tuple[int, str, str]]:
    """Return list of (subject_id, exp_type, date_yyyy_mm_dd)."""
    txt = csv_path.read_text(encoding="utf-8", errors="ignore")
    lines = [l.strip() for l in txt.splitlines()]
    current_section: str | None = None
    out: List[Tuple[int, str, str]] = []

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

        if current_section and cols and _is_int(cols[0]):
            try:
                tag = int(cols[0])
            except Exception:
                tag = None
            # Test Date typically in column index 4
            if tag is not None and len(cols) >= 5:
                d = _parse_date_mdY(cols[4])
                if d:
                    out.append((tag, current_section, d.strftime("%Y-%m-%d")))
        i += 1

    return out


# ------------------------------
# Master date QA helpers
# ------------------------------

SECTIONS = {
    "open field": "OF",
    "open field/arean habitation": "OF",
    "novel object | familiarization session": "FAM",
    "novel object | recognition session": "NOV",
}


def _parse_time_hhmm(s: str) -> tuple[int, int] | None:
    s = (s or "").strip()
    if not s:
        return None
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


def build_ground_truth(csv_path: Path) -> Dict[tuple[int, str], Set[str]]:
    """Return mapping: (tag_id, section) -> set of tokens 'YYYYMMDD_HHMM'"""
    txt = csv_path.read_text(encoding="utf-8", errors="ignore")
    lines = [l.strip() for l in txt.splitlines()]
    current_section: str | None = None
    gt: Dict[tuple[int, str], Set[str]] = {}

    i = 0
    while i < len(lines):
        raw = lines[i]
        cols = [c.strip() for c in raw.split(",")]
        key = cols[0].strip().lower()
        if key in SECTIONS:
            current_section = SECTIONS[key]
            i += 2
            continue
        if current_section and cols and _is_int(cols[0]):
            try:
                tag = int(cols[0])
            except Exception:
                tag = None
            if tag is not None and len(cols) >= 6:
                d = _parse_date_mdY(cols[4])
                tm = _parse_time_hhmm(cols[5])
                if d and tm:
                    dt = d.replace(hour=tm[0], minute=tm[1])
                    token = dt.strftime("%Y%m%d_%H%M")
                    gt.setdefault((tag, current_section), set()).add(token)
        i += 1
    return gt


def extract_token_from_filename(p: Path) -> tuple[int | None, str | None, str | None]:
    """Return (tag_id, section, token 'YYYYMMDD_HHMM' or None)."""
    stem = p.stem
    parts = stem.split("_")
    if len(parts) < 4:
        return None, None, None
    tag = None
    try:
        tag = int(parts[0])
    except Exception:
        pass
    section = parts[2].upper()
    if section not in {"OF", "FAM", "NOV"}:
        section = None
    token = None
    m = re.search(r"(20\d{6})_(\d{4})", stem)
    if m:
        token = f"{m.group(1)}_{m.group(2)}"
    return tag, section, token


