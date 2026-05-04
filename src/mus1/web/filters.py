"""Standardized filter / scope / mode-settings UI for mus1 panes.

Three concentric layers of state, defined by where the user expects to
find them:

* **Scope** — *which experiments are we operating on?* One cohort
  selector at the top of the sidebar, shared by every pane. Lives in
  ``st.session_state`` under :data:`SCOPE_KEY` so it survives navigation.

* **Filters** — *within scope, which experiments to show?* A standard
  set of widgets (marking status, QC status, genotype, sex, text search,
  date range). Each pane declares which filter fields apply via the
  ``fields=`` argument; widgets it doesn't enable are simply not
  rendered. Filter logic operates on row dicts produced by the
  per-pane discovery loaders, so loaders stay independent.

* **Mode settings** — *how should we render this experiment?*
  Pane-specific toggles (overlays, color choices, frame stride). Wrap
  them in :func:`mode_settings` so they always sit in the same expander
  on the sidebar.

The module is the single source of truth for filter rendering, so adding
a new universal filter (say, ``timepoint``) is one change in one place,
and every pane that opts in via ``fields={"timepoint", …}`` picks it up.

Conventions:

* Widget keys are scoped via :func:`pkey` (``"{pane}__{widget}"``) to
  prevent silent value-leakage between panes.
* Pure data lives in :class:`FilterState`. Pane code never reads/writes
  ``st.session_state`` directly for filter values; it goes through
  :func:`render_filters`.
* Cohort membership is resolved once per render via
  :func:`filter_by_cohort`; loaders never need to know about cohorts.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

import streamlit as st

from .discovery import CACHE_TTL_SECONDS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Session-state key that holds the current scope (cohort name or None).
SCOPE_KEY: str = "mus1_scope_cohort"

#: All filter field names that :func:`render_filters` understands.
KNOWN_FIELDS: FrozenSet[str] = frozenset(
    {"marking_status", "qc_statuses", "genotypes", "sexes", "text", "date_range"}
)

#: Allowed values for the marking-status widget.
MARKING_CHOICES: Tuple[str, ...] = ("any", "has", "needs")


# ---------------------------------------------------------------------------
# State container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FilterState:
    """Pure-data snapshot of the user's current filter selections.

    Default values represent "no filter" (i.e. show everything). An empty
    ``frozenset`` for the multi-select fields means "no restriction" —
    that's the convention every predicate here uses.
    """
    cohort: Optional[str] = None
    marking_status: str = "any"
    qc_statuses: FrozenSet[str] = field(default_factory=frozenset)
    genotypes: FrozenSet[str] = field(default_factory=frozenset)
    sexes: FrozenSet[str] = field(default_factory=frozenset)
    text: str = ""
    date_range: Tuple[Optional[date], Optional[date]] = (None, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pkey(pane: str, widget: str) -> str:
    """Build a unique Streamlit widget key namespaced to a pane.

    Avoids the silent state-bleed between panes that happens when two
    widgets share the same key (e.g. both having ``key="status"``).
    """
    return f"{pane}__{widget}"


def invalidate_after_write() -> None:
    """Clear every Streamlit data cache; call after any JSON write.

    Used by panes that mutate experiment JSONs or cohort manifests so
    the next render re-scans disk instead of serving the stale cached
    rows. Cheap (no I/O); safe to call unconditionally on the post-write
    code path.
    """
    try:
        st.cache_data.clear()
    except Exception:
        # Streamlit version or runtime context may not support .clear()
        # in every environment; failure here is non-fatal.
        pass


# ---------------------------------------------------------------------------
# Cohort-scope picker (top of sidebar, above the View radio)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _list_cohort_names(project_path_str: str) -> List[str]:
    """Return alphabetised cohort names from ``data/cohorts/*.json``."""
    cohorts_dir = Path(project_path_str) / "cohorts"
    if not cohorts_dir.is_dir():
        return []
    out: List[str] = []
    for p in sorted(cohorts_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            name = data.get("name") or p.stem
        except Exception:
            name = p.stem
        out.append(str(name))
    return out


def render_scope_banner() -> Optional[str]:
    """Render an inline caption showing the active cohort scope, if any.

    Call once near the top of each pane that honors the universal scope
    picker. Gives users a per-pane breadcrumb so the silent narrowing
    applied by :func:`render_filters` / :func:`filter_by_cohort` is
    discoverable without scanning the sidebar. Returns the active scope
    name (or None) so callers can branch on it without re-reading state.
    """
    scope = st.session_state.get(SCOPE_KEY)
    if scope:
        st.caption(
            f"Scope: cohort `{scope}` "
            "(set in sidebar — clear to see all experiments)."
        )
    return scope


def render_scope_picker(
    project_path: Path,
    *,
    key: str = SCOPE_KEY,
    label: str = "Scope (cohort)",
    help: str = (
        "Restrict every pane to members of this cohort. "
        "Choose 'All experiments' to disable scope filtering."
    ),
) -> Optional[str]:
    """Render the universal cohort selector at the top of the sidebar.

    Persists to ``st.session_state[key]`` so navigation between panes
    keeps the user's choice. Returns the selected cohort name, or
    ``None`` for "no scope".
    """
    names = _list_cohort_names(str(project_path))
    options: List[Optional[str]] = [None, *names]

    # Read previous value (may be None, "All experiments", or a name)
    current = st.session_state.get(key)
    try:
        idx = options.index(current)
    except ValueError:
        idx = 0  # default to "All experiments" if previous value is gone

    st.sidebar.subheader("Scope")
    selected = st.sidebar.selectbox(
        label,
        options=options,
        index=idx,
        format_func=lambda c: "All experiments" if c is None else c,
        key=key,
        help=help,
    )
    return selected


# ---------------------------------------------------------------------------
# Cohort filtering
# ---------------------------------------------------------------------------

def _cohort_member_ids(project_path: Path, cohort_name: str) -> Set[str]:
    """Return the set of experiment_ids in *cohort_name*.

    Resolves either by file stem ``cohorts/{cohort_name}.json`` or the
    JSON's ``name`` field. Returns an empty set on any error so a
    misconfigured scope never crashes the pane.
    """
    cohorts_dir = project_path / "cohorts"
    candidate = cohorts_dir / f"{cohort_name}.json"
    if not candidate.is_file():
        # Fall back to scanning by `name` field
        for p in cohorts_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text())
            except Exception:
                continue
            if data.get("name") == cohort_name:
                candidate = p
                break
        else:
            return set()
    try:
        data = json.loads(candidate.read_text())
    except Exception:
        return set()
    return {
        m["experiment_id"]
        for m in (data.get("members") or [])
        if isinstance(m, dict) and "experiment_id" in m
    }


def filter_by_cohort(
    rows: List[Dict[str, Any]],
    cohort_name: Optional[str],
    *,
    project_path: Path,
    id_field: str = "experiment_id",
) -> List[Dict[str, Any]]:
    """Restrict *rows* to members of *cohort_name*; pass through if None."""
    if not cohort_name:
        return rows
    member_ids = _cohort_member_ids(project_path, cohort_name)
    if not member_ids:
        return []
    return [r for r in rows if r.get(id_field) in member_ids]


# ---------------------------------------------------------------------------
# Filter widgets + predicates
# ---------------------------------------------------------------------------

def _coerce_bool(v: Any) -> Optional[bool]:
    """Treat truthy/falsy non-None values as bools; None is unknown."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return bool(v)


def _apply_marking_filter(
    rows: List[Dict[str, Any]],
    state: FilterState,
    marking_field: str,
) -> List[Dict[str, Any]]:
    if state.marking_status == "any":
        return rows
    want_has = state.marking_status == "has"
    out: List[Dict[str, Any]] = []
    for r in rows:
        v = _coerce_bool(r.get(marking_field))
        if v is None:
            continue  # unknown → drop on either branch
        if v == want_has:
            out.append(r)
    return out


def _apply_qc_filter(
    rows: List[Dict[str, Any]],
    state: FilterState,
    qc_field: str,
) -> List[Dict[str, Any]]:
    if not state.qc_statuses:
        return rows
    out: List[Dict[str, Any]] = []
    for r in rows:
        status = r.get(qc_field)
        if status is None or status == "":
            status = "unreviewed"
        if status in state.qc_statuses:
            out.append(r)
    return out


def _apply_choice_filter(
    rows: List[Dict[str, Any]],
    selected: FrozenSet[str],
    row_field: str,
) -> List[Dict[str, Any]]:
    if not selected:
        return rows
    return [r for r in rows if str(r.get(row_field, "")) in selected]


def _apply_text_filter(
    rows: List[Dict[str, Any]],
    needle: str,
    text_fields: Tuple[str, ...] = ("experiment_id", "subject_id"),
) -> List[Dict[str, Any]]:
    if not needle:
        return rows
    n = needle.lower()
    out: List[Dict[str, Any]] = []
    for r in rows:
        for f in text_fields:
            val = str(r.get(f, "")).lower()
            if n in val:
                out.append(r)
                break
    return out


def _parse_iso(d: str) -> Optional[date]:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except Exception:
        return None


def _apply_date_filter(
    rows: List[Dict[str, Any]],
    rng: Tuple[Optional[date], Optional[date]],
    date_field: str = "date_recorded",
) -> List[Dict[str, Any]]:
    lo, hi = rng
    if not lo and not hi:
        return rows
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = _parse_iso(str(r.get(date_field, "")))
        if d is None:
            continue
        if lo and d < lo:
            continue
        if hi and d > hi:
            continue
        out.append(r)
    return out


def _option_values(rows: List[Dict[str, Any]], field_name: str) -> List[str]:
    """Distinct, sorted values present in *rows* for a given column."""
    return sorted({str(r.get(field_name, "")) for r in rows if r.get(field_name)})


def render_filters(
    *,
    rows: List[Dict[str, Any]],
    fields: Set[str],
    key_prefix: str,
    marking_field: str = "has_marking",
    qc_field: str = "qc_status",
    expanded: bool = True,
    project_path: Optional[Path] = None,
    initial: Optional[FilterState] = None,
) -> Tuple[FilterState, List[Dict[str, Any]]]:
    """Render the standard ``Filters`` expander and return ``(state, filtered_rows)``.

    *fields* names which widgets to show — see :data:`KNOWN_FIELDS`. The
    cohort scope is read from :data:`SCOPE_KEY` (set by
    :func:`render_scope_picker`) and applied first, before any of the
    in-pane widgets. Pass *project_path* so cohort lookup can resolve.

    Pre-existing scope state is honored even if the calling pane forgot
    to render the scope picker — failing closed if cohorts can't be
    resolved.
    """
    if initial is None:
        initial = FilterState()

    unknown = fields - KNOWN_FIELDS
    if unknown:
        # Programmer error: keep tight feedback rather than silently ignoring
        raise ValueError(
            f"render_filters: unknown filter fields {sorted(unknown)}; "
            f"valid keys are {sorted(KNOWN_FIELDS)}."
        )

    cohort = st.session_state.get(SCOPE_KEY)
    if project_path is not None:
        rows = filter_by_cohort(rows, cohort, project_path=project_path)

    # Compute available option values from the cohort-scoped rows so the
    # widgets only offer choices that actually exist in scope.
    available_genotypes = _option_values(rows, "genotype")
    available_sexes = _option_values(rows, "sex")
    available_qc = sorted(
        {
            (str(r.get(qc_field)) if r.get(qc_field) else "unreviewed")
            for r in rows
        }
    )

    with st.sidebar.expander("Filters", expanded=expanded):
        marking_status = initial.marking_status
        if "marking_status" in fields:
            marking_status = st.radio(
                "Marking",
                options=list(MARKING_CHOICES),
                index=list(MARKING_CHOICES).index(initial.marking_status),
                key=pkey(key_prefix, "marking_status"),
                horizontal=True,
                help="`needs` = experiments missing the marking field; "
                     "`has` = experiments with it; `any` = no filter.",
            )

        qc_statuses: FrozenSet[str] = initial.qc_statuses
        if "qc_statuses" in fields and available_qc:
            sel = st.multiselect(
                "QC status",
                options=available_qc,
                default=list(initial.qc_statuses) if initial.qc_statuses else [],
                key=pkey(key_prefix, "qc_statuses"),
            )
            qc_statuses = frozenset(sel)

        genotypes: FrozenSet[str] = initial.genotypes
        if "genotypes" in fields and available_genotypes:
            sel = st.multiselect(
                "Genotype",
                options=available_genotypes,
                default=list(initial.genotypes) if initial.genotypes else [],
                key=pkey(key_prefix, "genotypes"),
            )
            genotypes = frozenset(sel)

        sexes: FrozenSet[str] = initial.sexes
        if "sexes" in fields and available_sexes:
            sel = st.multiselect(
                "Sex",
                options=available_sexes,
                default=list(initial.sexes) if initial.sexes else [],
                key=pkey(key_prefix, "sexes"),
            )
            sexes = frozenset(sel)

        text = initial.text
        if "text" in fields:
            text = st.text_input(
                "Search (id / subject)",
                value=initial.text,
                key=pkey(key_prefix, "text"),
            )

        date_range = initial.date_range
        if "date_range" in fields:
            existing_dates = sorted(
                {
                    _parse_iso(str(r.get("date_recorded", "")))
                    for r in rows
                }
                - {None}
            )
            if existing_dates:
                lo_default = initial.date_range[0] or existing_dates[0]
                hi_default = initial.date_range[1] or existing_dates[-1]
                lo, hi = st.date_input(
                    "Date range",
                    value=(lo_default, hi_default),
                    min_value=existing_dates[0],
                    max_value=existing_dates[-1],
                    key=pkey(key_prefix, "date_range"),
                )
                if isinstance(lo, tuple):  # streamlit returns tuple when both set
                    date_range = lo
                else:
                    date_range = (lo, hi)

    state = FilterState(
        cohort=cohort,
        marking_status=marking_status,
        qc_statuses=qc_statuses,
        genotypes=genotypes,
        sexes=sexes,
        text=text,
        date_range=date_range,
    )

    if "marking_status" in fields:
        rows = _apply_marking_filter(rows, state, marking_field)
    if "qc_statuses" in fields:
        rows = _apply_qc_filter(rows, state, qc_field)
    if "genotypes" in fields:
        rows = _apply_choice_filter(rows, state.genotypes, "genotype")
    if "sexes" in fields:
        rows = _apply_choice_filter(rows, state.sexes, "sex")
    if "text" in fields:
        rows = _apply_text_filter(rows, state.text)
    if "date_range" in fields:
        rows = _apply_date_filter(rows, state.date_range)

    return state, rows


# ---------------------------------------------------------------------------
# Mode-settings expander
# ---------------------------------------------------------------------------

@contextmanager
def mode_settings(
    label: str = "Display",
    *,
    key_prefix: str,
    expanded: bool = False,
) -> Iterator[None]:
    """Context manager that opens the standard ``Display`` expander.

    Use it to wrap pane-specific toggles (``show_trajectory``,
    ``frame_stride``, …). The convention is that mode settings belong
    *here*, after the View radio and the Filters block, so users always
    know where to look.

    Example::

        with mode_settings("Display", key_prefix="ezm_zones"):
            show_traj = st.checkbox("Show trajectory", value=True,
                                    key=pkey("ezm_zones", "show_traj"))
    """
    with st.sidebar.expander(label, expanded=expanded):
        yield
