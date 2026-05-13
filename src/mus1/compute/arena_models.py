"""Active arena U-Net model registry (per-profile).

Reads ``<project_path>/arena_models.yaml`` and returns the currently
active checkpoint for each :class:`mus1.arena_profiles.ArenaProfile`.
The file is the single source of truth for "which trained model
should the app use right now for profile X". Activation discipline:
the QC and inference panes pin the active ``run_id`` onto every write
so historical reviews stay anchored to the model they were performed
against (per user 2026-05-07 confirmation).

YAML schema::

    arena_models:
      ezm_460mm:
        active:
          run_id: ezm_unet_20260120_lr01_bs8
          checkpoint: ml_workspace/ezm_arena_unet/active_model/model_best.pt
          n_classes: 3
          mask_to_marking: ezm_wedge_points
          activated_at: "2026-04-15T12:00:00Z"
          notes: "Best so far on validation cohort."
      tamco_black_bucket:
        active: null
      home_depot_5gal_orange:
        active: null

Top-level ``arena_models`` is a mapping ``profile_id -> {active: ...}``.
``active: null`` (or the entry being absent) means "no model trained
yet" — callers must surface that gracefully rather than substituting a
guess.

Pure-Python; no torch / cv2 / streamlit dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover  (PyYAML is a project dependency)
    yaml = None


PROJECT_MODELS_FILENAME = "arena_models.yaml"


@dataclass(frozen=True)
class ActiveArenaModel:
    """The currently-active U-Net for a single arena profile."""
    profile_id: str
    run_id: str
    checkpoint: Path  # absolute path
    n_classes: int = 3
    mask_to_marking: str = ""  # post-processor key; "" means "mask only"
    activated_at: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "run_id": self.run_id,
            "checkpoint": str(self.checkpoint),
            "n_classes": self.n_classes,
            "mask_to_marking": self.mask_to_marking,
            "activated_at": self.activated_at,
            "notes": self.notes,
        }


@dataclass
class ArenaModelRegistry:
    """In-memory map ``profile_id -> ActiveArenaModel`` (or absent for inactive)."""
    project_path: Optional[Path] = None
    _entries: Dict[str, ActiveArenaModel] = field(default_factory=dict)
    _source_path: Optional[Path] = None

    def get(self, profile_id: str) -> Optional[ActiveArenaModel]:
        """Return the active model for *profile_id*, or ``None`` if inactive."""
        return self._entries.get(profile_id)

    def list_profiles(self) -> list[str]:
        """Return profile_ids that have an active model registered."""
        return sorted(self._entries.keys())

    def is_active(self, profile_id: str) -> bool:
        return profile_id in self._entries

    @property
    def source_path(self) -> Optional[Path]:
        """Return the YAML path this registry was loaded from, or ``None``."""
        return self._source_path

    @classmethod
    def load(cls, project_path: Optional[Path] = None) -> "ArenaModelRegistry":
        """Read ``<project_path>/arena_models.yaml`` if present, else return empty.

        Missing file is a no-op; the registry simply reports no profiles
        as active. Malformed YAML raises ``ValueError``.
        """
        registry = cls(project_path=Path(project_path) if project_path else None)
        if project_path is None:
            return registry
        yaml_path = Path(project_path) / PROJECT_MODELS_FILENAME
        if not yaml_path.is_file():
            return registry
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to read arena_models.yaml but is not installed."
            )
        try:
            with yaml_path.open("r") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"{yaml_path} is not valid YAML: {e}")
        if not isinstance(data, dict):
            raise ValueError(f"{yaml_path}: top-level must be a mapping")
        models_raw = data.get("arena_models") or {}
        if not isinstance(models_raw, dict):
            raise ValueError(f"{yaml_path}: `arena_models` must be a mapping")

        registry._source_path = yaml_path
        for profile_id, entry in models_raw.items():
            if not isinstance(profile_id, str) or not profile_id.strip():
                continue
            if not isinstance(entry, dict):
                continue
            active = entry.get("active")
            if not active:  # explicit null / missing / empty dict
                continue
            if not isinstance(active, dict):
                raise ValueError(
                    f"{yaml_path}: arena_models.{profile_id}.active must be a mapping or null"
                )
            registry._register_from_payload(profile_id, active, base_dir=yaml_path.parent)
        return registry

    @staticmethod
    def write_active(
        project_path: Path,
        *,
        profile_id: str,
        run_id: str,
        checkpoint: Path,
        n_classes: int = 3,
        mask_to_marking: str = "",
        notes: str = "",
    ) -> Path:
        """Persist an ``active`` entry for *profile_id* into
        ``<project_path>/arena_models.yaml``, preserving any other
        profiles already in the file.

        Returns the path written. Raises ``FileNotFoundError`` when the
        checkpoint doesn't exist on disk (callers should validate first
        if they want to surface a friendlier error).
        """
        try:
            import yaml  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "PyYAML required to write arena_models.yaml"
            ) from e
        ckpt = Path(checkpoint)
        if not ckpt.is_file():
            raise FileNotFoundError(f"checkpoint not found: {ckpt}")
        yaml_path = Path(project_path) / PROJECT_MODELS_FILENAME
        if yaml_path.is_file():
            with yaml_path.open("r") as f:
                doc = yaml.safe_load(f) or {}
        else:
            doc = {}
        models = doc.setdefault("arena_models", {})
        if not isinstance(models, dict):
            raise ValueError(
                f"{yaml_path}: arena_models must be a mapping"
            )
        models[profile_id] = {
            "active": {
                "run_id": run_id,
                "checkpoint": str(ckpt),
                "n_classes": int(n_classes),
                "mask_to_marking": mask_to_marking,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "notes": notes,
            }
        }
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with yaml_path.open("w") as f:
            yaml.safe_dump(doc, f, sort_keys=False)
        return yaml_path

    @staticmethod
    def clear_active(project_path: Path, *, profile_id: str) -> Optional[Path]:
        """Set ``arena_models.{profile_id}.active = null``. Returns the
        yaml path written, or ``None`` if no file existed."""
        try:
            import yaml  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("PyYAML required") from e
        yaml_path = Path(project_path) / PROJECT_MODELS_FILENAME
        if not yaml_path.is_file():
            return None
        with yaml_path.open("r") as f:
            doc = yaml.safe_load(f) or {}
        models = doc.get("arena_models") or {}
        if profile_id in models:
            models[profile_id] = {"active": None}
            with yaml_path.open("w") as f:
                yaml.safe_dump(doc, f, sort_keys=False)
        return yaml_path

    def _register_from_payload(
        self, profile_id: str, active: Mapping[str, Any], *, base_dir: Path,
    ) -> None:
        run_id = str(active.get("run_id") or "").strip()
        ckpt_raw = str(active.get("checkpoint") or "").strip()
        if not run_id or not ckpt_raw:
            raise ValueError(
                f"arena_models.{profile_id}.active requires run_id and checkpoint"
            )
        # Resolve checkpoint relative to project_path's parent (the WDMOSEQ2 root)
        # so paths like "ml_workspace/..." just work. Absolute paths pass through.
        ckpt_path = Path(ckpt_raw)
        if not ckpt_path.is_absolute():
            # Try project_path first, then project_path.parent (workspace root).
            for candidate in (base_dir / ckpt_raw, base_dir.parent / ckpt_raw):
                if candidate.exists():
                    ckpt_path = candidate
                    break
            else:
                # Keep the relative-resolved path (workspace-root anchored) so
                # callers can produce a meaningful error without us crashing on load.
                ckpt_path = (base_dir.parent / ckpt_raw).resolve()
        n_classes = int(active.get("n_classes", 3))
        mask_to_marking = str(active.get("mask_to_marking") or "").strip()
        activated_at = str(active.get("activated_at") or "").strip()
        notes = str(active.get("notes") or "").strip()
        self._entries[profile_id] = ActiveArenaModel(
            profile_id=profile_id,
            run_id=run_id,
            checkpoint=ckpt_path,
            n_classes=n_classes,
            mask_to_marking=mask_to_marking,
            activated_at=activated_at,
            notes=notes,
        )
