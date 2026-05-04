"""User-level preferences: cluster behavior, GPU defaults, compute thresholds.

Schema is intentionally small and explicit. Two cascading sources, in
override order (latter wins):

  1. ``~/.config/mus1/preferences.yaml``         — user-level
  2. ``<project_path>/data/mus1.preferences.yaml`` — project-level

Either file is optional; missing files contribute their defaults via the
`Preferences` dataclass below. Agents (Claude Code etc.) populate these
files when the user describes their cluster habits in chat; the app
reads them at job-submission time and to seed compute thresholds.

This module is **read-mostly and pure-Python**: no dependency on
Streamlit, FastAPI, or the compute library. It's safe to import from
the CLI, the web app, the harness, and tests.

Example user-level YAML::

    cluster:
      partitions:
        - name: bio
          prefer_idle_nodes: true
          max_jobs_per_node: 1
          role: primary
        - name: t1small
          max_jobs_per_node: 1
          role: overflow
      gpu:
        default_partitions: [gpu]            # (future: gpu / bio_gpu)
        jobs_requiring_gpu: [kpms_fit, dlc_inference, ezm_unet_training]

    compute:
      tracking_confidence:
        pcutoff: 0.6
        overall_frac_threshold: 0.80
        bodypart_frac_threshold: 0.50
        dropout_min_frames: 30
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover — PyYAML is in pyproject deps
    yaml = None


# ---------------------------------------------------------------------------
# Defaults (inline so missing files are not a hard error anywhere)
# ---------------------------------------------------------------------------

DEFAULT_USER_PREFS_PATH = Path("~/.config/mus1/preferences.yaml").expanduser()
PROJECT_PREFS_FILENAME = "mus1.preferences.yaml"


@dataclass
class PartitionPref:
    """A Slurm partition with submission policy."""
    name: str
    prefer_idle_nodes: bool = False
    max_jobs_per_node: int = 1
    role: str = "primary"  # "primary" | "overflow" | "gpu"


@dataclass
class GPUPref:
    """GPU-specific submission policy.

    *Currently a placeholder for future cluster GPU support.* No code
    path consumes this yet; documented here so the schema stabilizes
    before Job Manager (Phase D) wires it.
    """
    default_partitions: List[str] = field(default_factory=list)
    jobs_requiring_gpu: List[str] = field(default_factory=list)


@dataclass
class ClusterPref:
    """Slurm-cluster preferences."""
    partitions: List[PartitionPref] = field(default_factory=list)
    gpu: GPUPref = field(default_factory=GPUPref)

    def primary(self) -> Optional[PartitionPref]:
        for p in self.partitions:
            if p.role == "primary":
                return p
        return self.partitions[0] if self.partitions else None

    def overflow(self) -> List[PartitionPref]:
        return [p for p in self.partitions if p.role == "overflow"]


@dataclass
class TrackingConfidenceThresholds:
    """Override thresholds for ``mus1.compute.tracking_confidence``."""
    pcutoff: float = 0.6
    overall_frac_threshold: float = 0.80
    bodypart_frac_threshold: float = 0.50
    dropout_min_frames: int = 30


@dataclass
class ComputePref:
    """Per-module compute knobs that are user-tunable."""
    tracking_confidence: TrackingConfidenceThresholds = field(
        default_factory=TrackingConfidenceThresholds)


@dataclass
class Preferences:
    """Top-level container."""
    cluster: ClusterPref = field(default_factory=ClusterPref)
    compute: ComputePref = field(default_factory=ComputePref)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Built-in defaults (factory; do not mutate)
# ---------------------------------------------------------------------------

def default_preferences() -> Preferences:
    """Return a fresh ``Preferences`` with documented defaults.

    Defaults match what's in CLAUDE.md (bio idle-first → t1small overflow,
    1 job per node) so agents that have read the project conventions
    produce a config consistent with project-wide practice when they
    seed the file.
    """
    return Preferences(
        cluster=ClusterPref(
            partitions=[
                PartitionPref(name="bio", prefer_idle_nodes=True,
                              max_jobs_per_node=1, role="primary"),
                PartitionPref(name="t1small", prefer_idle_nodes=False,
                              max_jobs_per_node=1, role="overflow"),
            ],
            gpu=GPUPref(
                default_partitions=[],   # populated when GPU partitions land
                jobs_requiring_gpu=[],
            ),
        ),
        compute=ComputePref(
            tracking_confidence=TrackingConfidenceThresholds(),
        ),
    )


# ---------------------------------------------------------------------------
# Loader (cascade)
# ---------------------------------------------------------------------------

def load_preferences(
    project_path: Optional[Path | str] = None,
    *,
    user_path: Optional[Path | str] = None,
) -> Preferences:
    """Load preferences, cascading user → project.

    Either layer may be absent; missing files contribute their defaults.
    A malformed YAML file is reported (raises ``ValueError``) rather
    than silently dropped — preferences drive cluster submission, so a
    silent fallback could send work to the wrong partition.
    """
    prefs = default_preferences()

    user_yaml = _read_yaml(Path(user_path) if user_path else DEFAULT_USER_PREFS_PATH)
    if user_yaml:
        prefs = _merge_into(prefs, user_yaml, layer="user")

    if project_path is not None:
        proj_path = Path(project_path) / "data" / PROJECT_PREFS_FILENAME
        proj_yaml = _read_yaml(proj_path)
        if proj_yaml:
            prefs = _merge_into(prefs, proj_yaml, layer="project")

    return prefs


def _read_yaml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to read mus1 preferences but is not installed. "
            "It is listed in pyproject.toml dependencies; ensure your env is up to date."
        )
    try:
        with path.open("r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"preferences file {path} is not valid YAML: {e}")
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(
            f"preferences file {path} must contain a mapping at top level, "
            f"got {type(data).__name__}"
        )
    return data


def _merge_into(prefs: Preferences, override: Dict[str, Any], *, layer: str) -> Preferences:
    """Apply *override* (raw YAML dict) on top of *prefs*. Returns a new instance."""
    cluster_raw = override.get("cluster") or {}
    if cluster_raw:
        partitions_raw = cluster_raw.get("partitions")
        if partitions_raw is not None:
            if not isinstance(partitions_raw, list):
                raise ValueError(f"[{layer}] cluster.partitions must be a list")
            prefs.cluster.partitions = [
                PartitionPref(
                    name=str(p.get("name", "")),
                    prefer_idle_nodes=bool(p.get("prefer_idle_nodes", False)),
                    max_jobs_per_node=int(p.get("max_jobs_per_node", 1)),
                    role=str(p.get("role", "primary")),
                )
                for p in partitions_raw
                if isinstance(p, dict) and p.get("name")
            ]
        gpu_raw = cluster_raw.get("gpu") or {}
        if gpu_raw:
            prefs.cluster.gpu = GPUPref(
                default_partitions=list(gpu_raw.get("default_partitions") or []),
                jobs_requiring_gpu=list(gpu_raw.get("jobs_requiring_gpu") or []),
            )

    compute_raw = override.get("compute") or {}
    if compute_raw:
        tc_raw = compute_raw.get("tracking_confidence") or {}
        if tc_raw:
            cur = prefs.compute.tracking_confidence
            prefs.compute.tracking_confidence = TrackingConfidenceThresholds(
                pcutoff=float(tc_raw.get("pcutoff", cur.pcutoff)),
                overall_frac_threshold=float(tc_raw.get(
                    "overall_frac_threshold", cur.overall_frac_threshold)),
                bodypart_frac_threshold=float(tc_raw.get(
                    "bodypart_frac_threshold", cur.bodypart_frac_threshold)),
                dropout_min_frames=int(tc_raw.get(
                    "dropout_min_frames", cur.dropout_min_frames)),
            )

    return prefs


# ---------------------------------------------------------------------------
# Seed helper (used by `mus1 setup preferences`)
# ---------------------------------------------------------------------------

def write_default_user_preferences(path: Optional[Path | str] = None) -> Path:
    """Write a defaults YAML file to *path* (user-level by default).

    Existing files are left alone — this is for first-run seeding only.
    Returns the path written (or the existing path if already there).
    """
    target = Path(path) if path else DEFAULT_USER_PREFS_PATH
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if yaml is None:
        raise RuntimeError("PyYAML is required to write preferences.")
    payload = default_preferences().to_dict()
    with target.open("w") as f:
        yaml.safe_dump(payload, f, sort_keys=False)
    return target
