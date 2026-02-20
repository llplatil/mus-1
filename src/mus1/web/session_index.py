from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from .paths import resolve_session_index_csv


@st.cache_data(show_spinner=False)
def load_session_index_map(workspace_root: str) -> Optional[Dict[Tuple[str, str], Dict[str, Any]]]:
    """
    Load session_index_filtered.csv and build (task, basename) -> row mapping.
    Keeps only keys that are unique in the CSV.
    """
    if not workspace_root:
        return None
    try:
        import pandas as pd
    except Exception:
        return None

    csv_path = resolve_session_index_csv(workspace_root)
    if not csv_path:
        return None
    df = pd.read_csv(csv_path)
    if "video_path" not in df.columns or "task" not in df.columns:
        return None
    vps = df["video_path"].fillna("").astype(str).str.strip()
    df = df.loc[vps.ne("")].copy()
    df["basename"] = df["video_path"].astype(str).apply(lambda s: Path(s).name)
    grouped = df.groupby(["task", "basename"]).size()
    unique_keys = set(k for k, n in grouped.items() if int(n) == 1)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, r in df.iterrows():
        task = str(r.get("task", "")).strip()
        bn = str(r.get("basename", "")).strip()
        key = (task, bn)
        if key not in unique_keys:
            continue
        out[key] = {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}
    return out


@st.cache_data(show_spinner=False)
def read_session_index_rows(
    workspace_root: str,
    *,
    tasks: Optional[List[str]] = None,
    require_video_path: bool = True,
) -> List[Dict[str, str]]:
    """
    Lightweight CSV reader for session_index_filtered.csv.
    Returns list of row dicts with string values.
    """
    csv_path = resolve_session_index_csv(workspace_root)
    if not csv_path:
        return []

    want = {str(t).strip().upper() for t in (tasks or []) if str(t).strip()}
    out: List[Dict[str, str]] = []
    with Path(csv_path).open(newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            task = str((row.get("task") or "")).strip().upper()
            vp = str((row.get("video_path") or "")).strip()
            if want and task not in want:
                continue
            if require_video_path and not vp:
                continue
            out.append({k: ("" if v is None else str(v)) for k, v in row.items()})
    return out

