#!/usr/bin/env python3
"""Migrate raw annotation points from EZM per-video zone JSONs into experiment JSONs.

Reads zone JSONs from:
    apps/mus1/workspace/arena_zones/ezm_per_video_v2/*.json

Writes into each matching experiment JSON's arena_markings:
    - ezm_wedge_points  (4 border points, from wedge_refinement method)
    - ezm_boundary_points  (outer + inner clicked points, from original 4-step method)

Mapping: zone JSON video_stem -> experiment JSON video.filename stem.

Usage:
    python migrate_ezm_zone_jsons_to_arena_markings.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ZONE_DIR = PROJECT_ROOT / "apps" / "mus1" / "workspace" / "arena_zones" / "ezm_per_video_v2"
EZM_EXP_DIR = PROJECT_ROOT / "data" / "experiment_data" / "EZM"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_video_stem_to_experiment(ezm_dir: Path) -> Dict[str, Tuple[str, Path]]:
    """Map video filename stems to (experiment_id, json_path)."""
    mapping: Dict[str, Tuple[str, Path]] = {}
    for exp_dir in sorted(ezm_dir.iterdir()):
        if not exp_dir.is_dir():
            continue
        jsons = [f for f in exp_dir.iterdir() if f.suffix == ".json"]
        if not jsons:
            continue
        jf = jsons[0]
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        vid_filename = (data.get("video") or {}).get("filename", "")
        if vid_filename:
            stem = Path(vid_filename).stem
            mapping[stem] = (data.get("experiment_id", ""), jf)
    return mapping


def _extract_circle_points(canvas: dict, pt_radius: float = 8.0) -> List[List[float]]:
    """Extract [x, y] center coords from Fabric.js canvas circle objects.

    Fabric.js point mode: originX="left" so left = circle left edge.
    Add pt_radius to get center. originY="center" so top is center-y.
    """
    points = []
    for obj in (canvas.get("objects") or []):
        if obj.get("type") == "circle":
            cx = obj.get("left", 0) + pt_radius
            cy = obj.get("top", 0)
            points.append([round(cx, 1), round(cy, 1)])
    return points


def _migrate_one(
    zone_path: Path,
    exp_json_path: Path,
    experiment_id: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Migrate one zone JSON's raw points into the experiment JSON.

    Returns a log dict.
    """
    zd = json.loads(zone_path.read_text())
    ann = zd.get("annotations") or {}
    method = ann.get("method")
    image = zd.get("image") or {}
    frame_shape = [image.get("height", 0), image.get("width", 0)]

    log: Dict[str, Any] = {
        "zone_file": zone_path.name,
        "experiment_id": experiment_id,
        "method": method,
    }

    # Read experiment JSON
    exp_data = json.loads(exp_json_path.read_text())
    am = exp_data.get("arena_markings") or {}

    if method == "wedge_refinement":
        # Extract 4 wedge border points (2 per wedge)
        w1 = ann.get("wedge1_border_pts_img") or []
        w2 = ann.get("wedge2_border_pts_img") or []
        all_pts = w1 + w2  # 4 points total
        if len(all_pts) == 4:
            am["ezm_wedge_points"] = {
                "points": [[round(p[0], 1), round(p[1], 1)] for p in all_pts],
                "frame_shape": frame_shape,
                "flag_review": False,
                "note": "",
                "marked_at": _now_iso(),
                "source": "migrated_from_zone_json_v2_wedge_refinement",
            }
            log["wedge_points"] = len(all_pts)
        else:
            log["wedge_points_error"] = f"expected 4, got {len(all_pts)}"

    else:
        # Original 4-step method: extract outer/inner canvas points
        outer_canvas = ann.get("outer_canvas") or {}
        inner_canvas = ann.get("inner_canvas") or {}

        # The original annotation uses display coordinates with a pt_radius
        # Canvas objects store points at display scale; check for coord_space
        coord_space = ann.get("coord_space", "display")
        pt_r = 8.0 if coord_space == "display" else 0.0

        outer_pts = _extract_circle_points(outer_canvas, pt_r)
        inner_pts = _extract_circle_points(inner_canvas, pt_r)

        if outer_pts or inner_pts:
            am["ezm_boundary_points"] = {
                "outer_points": outer_pts,
                "inner_points": inner_pts,
                "frame_shape": frame_shape,
                "source": "migrated_from_zone_json_v2_4step",
                "migrated_at": _now_iso(),
            }
            log["outer_points"] = len(outer_pts)
            log["inner_points"] = len(inner_pts)

        # Also extract border lines (4-step has border canvas with line objects)
        borders_canvas = ann.get("borders_canvas") or {}
        border_objs = borders_canvas.get("objects") or []
        if border_objs:
            border_lines = []
            for obj in border_objs:
                if obj.get("type") == "line":
                    x1 = float(obj.get("x1", 0)) + float(obj.get("left", 0))
                    y1 = float(obj.get("y1", 0)) + float(obj.get("top", 0))
                    x2 = float(obj.get("x2", 0)) + float(obj.get("left", 0))
                    y2 = float(obj.get("y2", 0)) + float(obj.get("top", 0))
                    border_lines.append([[round(x1, 1), round(y1, 1)], [round(x2, 1), round(y2, 1)]])
            if border_lines:
                am["ezm_boundary_points"]["border_lines"] = border_lines
                log["border_lines"] = len(border_lines)

    exp_data["arena_markings"] = am

    if not dry_run:
        exp_json_path.write_text(json.dumps(exp_data, indent=2, default=str) + "\n")
        log["written"] = True
    else:
        log["written"] = False

    return log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Don't write; just print what would happen.")
    args = parser.parse_args()

    if not ZONE_DIR.is_dir():
        print(f"Zone directory not found: {ZONE_DIR}")
        return
    if not EZM_EXP_DIR.is_dir():
        print(f"Experiment directory not found: {EZM_EXP_DIR}")
        return

    # Build mapping
    stem_to_exp = _build_video_stem_to_experiment(EZM_EXP_DIR)
    print(f"Found {len(stem_to_exp)} EZM experiments with video filenames")

    # Iterate zone JSONs
    zone_files = sorted(f for f in ZONE_DIR.glob("*.json") if ".bak" not in f.name)
    print(f"Found {len(zone_files)} zone JSONs")

    logs: List[Dict[str, Any]] = []
    matched = 0
    unmatched = []

    for zf in zone_files:
        zone_stem = zf.name.replace("_ezm_open_closed_v2.json", "")
        if zone_stem in stem_to_exp:
            exp_id, exp_json = stem_to_exp[zone_stem]
            log = _migrate_one(zf, exp_json, exp_id, dry_run=args.dry_run)
            logs.append(log)
            matched += 1
        else:
            unmatched.append(zone_stem)

    # Summary
    print(f"\nMatched and migrated: {matched}")
    if unmatched:
        print(f"Unmatched (no experiment JSON found): {len(unmatched)}")
        for u in unmatched:
            print(f"  {u}")

    wedge_count = sum(1 for l in logs if l.get("wedge_points"))
    boundary_count = sum(1 for l in logs if l.get("outer_points"))
    print(f"  Wedge point migrations: {wedge_count}")
    print(f"  Boundary point migrations: {boundary_count}")

    if args.dry_run:
        print("\n[DRY RUN] No files were modified.")
    else:
        print(f"\nDone. {matched} experiment JSONs updated.")


if __name__ == "__main__":
    main()
