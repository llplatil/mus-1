"""Tests for the Arena Training inference launcher (T17)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mus1.web.arena_inference_launcher import (
    RUN_ARTIFACT_KIND,
    RUN_KIND_SLUG,
    build_command,
    launch,
    make_run_id,
    prepare_run_dir,
    register_run_artifact,
    relevant_cohorts_for_profile,
)


# ---------------------------------------------------------------------------
# make_run_id
# ---------------------------------------------------------------------------

def test_make_run_id_includes_profile_cohort_timestamp():
    now = datetime(2026, 6, 1, 12, 30, 45, tzinfo=timezone.utc)
    rid = make_run_id(profile_id="ezm_460mm", cohort="ezm_publication", now=now)
    assert rid.startswith("20260601_123045__ezm_460mm__")
    assert rid.endswith("ezm_publication")


def test_make_run_id_sanitizes_cohort_name():
    now = datetime(2026, 6, 1, 12, 30, 45, tzinfo=timezone.utc)
    rid = make_run_id(profile_id="ezm_460mm", cohort="weird name/with/slashes", now=now)
    # Slashes + spaces become underscores so it's filesystem-safe
    assert "/" not in rid
    assert " " not in rid


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------

def test_build_command_minimal():
    cmd = build_command(
        profile_id="ezm_460mm", cohort="ezm_publication",
        project_path=Path("/tmp/data"),
        python_executable="/usr/bin/python3",
    )
    assert cmd[:5] == ["/usr/bin/python3", "-m", "mus1", "arena-inference", "run"]
    assert "ezm_460mm" in cmd
    assert "--cohort" in cmd and "ezm_publication" in cmd
    assert "--project-path" in cmd and "/tmp/data" in cmd
    assert "--frames-per-video" in cmd
    assert "--overwrite" not in cmd
    assert "--limit" not in cmd


def test_build_command_with_overwrite_and_limit():
    cmd = build_command(
        profile_id="tamco_black_bucket", cohort="validation_2026",
        project_path=Path("/tmp/data"),
        frames_per_video=10, overwrite=True, limit=5,
        python_executable="/usr/bin/python3",
    )
    assert "--overwrite" in cmd
    assert "--limit" in cmd and "5" in cmd
    idx = cmd.index("--frames-per-video")
    assert cmd[idx + 1] == "10"


# ---------------------------------------------------------------------------
# prepare_run_dir
# ---------------------------------------------------------------------------

def test_prepare_run_dir_creates_dir_and_status(tmp_path: Path):
    run_dir, run_id = prepare_run_dir(
        project_path=tmp_path,
        profile_id="ezm_460mm", cohort="ezm_publication",
        command=["python", "-m", "mus1"],
    )
    assert run_dir.is_dir()
    assert run_dir.parent.name == RUN_KIND_SLUG
    assert run_dir.parent.parent.name == "runs"
    status_path = run_dir / "run_status.json"
    assert status_path.is_file()
    status = json.loads(status_path.read_text())
    assert status["state"] == "queued"
    assert status["profile_id"] == "ezm_460mm"
    assert status["cohort"] == "ezm_publication"
    assert status["run_id"] == run_id
    assert status["command"] == ["python", "-m", "mus1"]


def test_prepare_run_dir_collides_when_run_id_reused(tmp_path: Path):
    now = datetime(2026, 6, 1, 12, 30, 45, tzinfo=timezone.utc)
    prepare_run_dir(
        project_path=tmp_path, profile_id="ezm_460mm",
        cohort="ezm_publication", command=["x"], now=now,
    )
    # Same timestamp → same run_id → mkdir(exist_ok=False) raises
    with pytest.raises(FileExistsError):
        prepare_run_dir(
            project_path=tmp_path, profile_id="ezm_460mm",
            cohort="ezm_publication", command=["x"], now=now,
        )


# ---------------------------------------------------------------------------
# register_run_artifact
# ---------------------------------------------------------------------------

def test_register_run_artifact_skips_when_no_db(tmp_path: Path):
    """Missing DB file → returns False, doesn't raise."""
    result = register_run_artifact(
        db_path=tmp_path / "nonexistent.db",
        run_dir=tmp_path / "runs" / "arena_inference" / "fake",
        run_id="fake",
        profile_id="ezm_460mm",
        cohort="ezm_publication",
    )
    assert result is False


def test_register_run_artifact_writes_and_dedupes(tmp_path: Path):
    """Inserts the row on first call; returns False on duplicate."""
    db_path = tmp_path / "mus1.db"
    from mus1.core.schema import Database
    # Touch the DB so register_run_artifact's is_file() check passes
    Database(str(db_path)).create_tables()
    run_dir = tmp_path / "runs" / RUN_KIND_SLUG / "r1"
    run_dir.mkdir(parents=True)

    first = register_run_artifact(
        db_path=db_path, run_dir=run_dir, run_id="r1",
        profile_id="ezm_460mm", cohort="ezm_publication",
    )
    second = register_run_artifact(
        db_path=db_path, run_dir=run_dir, run_id="r1",
        profile_id="ezm_460mm", cohort="ezm_publication",
    )
    assert first is True
    assert second is False  # already exists


# ---------------------------------------------------------------------------
# launch (dry_run only — don't fork a real subprocess in tests)
# ---------------------------------------------------------------------------

def test_launch_dry_run_prepares_dir_without_subprocess(tmp_path: Path):
    result = launch(
        project_path=tmp_path, db_path=None,
        profile_id="ezm_460mm", cohort="ezm_publication",
        dry_run=True,
    )
    assert result.pid is None
    assert result.run_dir.is_dir()
    assert result.status_path.is_file()
    status = json.loads(result.status_path.read_text())
    # state stays at "queued" — running state is only set after real subprocess
    assert status["state"] == "queued"
    # Logs not yet created (subprocess didn't run)
    assert not result.stdout_log.exists()
    assert not result.stderr_log.exists()


def test_launch_dry_run_registers_artifact_when_db_exists(tmp_path: Path):
    db_path = tmp_path / "mus1.db"
    from mus1.core.schema import Database
    Database(str(db_path)).create_tables()

    result = launch(
        project_path=tmp_path, db_path=db_path,
        profile_id="ezm_460mm", cohort="ezm_publication",
        dry_run=True,
    )
    # Verify the artifact landed in the DB
    import sqlite3
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT kind, path FROM external_artifacts WHERE kind = ?",
        (RUN_ARTIFACT_KIND,),
    ).fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0][0] == RUN_ARTIFACT_KIND
    assert rows[0][1] == str(result.run_dir)


# ---------------------------------------------------------------------------
# relevant_cohorts_for_profile
# ---------------------------------------------------------------------------

def test_relevant_cohorts_empty_when_no_cohorts_dir(tmp_path: Path):
    assert relevant_cohorts_for_profile(
        project_path=tmp_path, profile_id="ezm_460mm",
    ) == []


def test_relevant_cohorts_filters_by_profile_task_default(tmp_path: Path):
    """A cohort with task_types matching the profile's defaulting tasks is
    returned; cohorts without overlap are filtered out."""
    cohorts_dir = tmp_path / "cohorts"
    cohorts_dir.mkdir()
    # EZM task defaults to ezm_460mm; NOR/NOF/OF default to tamco_black_bucket
    (cohorts_dir / "ezm_pub.json").write_text(json.dumps({
        "name": "ezm_pub", "task_types": ["EZM"], "members": [],
    }))
    (cohorts_dir / "nor_pub.json").write_text(json.dumps({
        "name": "nor_pub", "task_types": ["NOR", "NOF"], "members": [],
    }))
    (cohorts_dir / "rr_pub.json").write_text(json.dumps({
        "name": "rr_pub", "task_types": ["RR"], "members": [],
    }))
    # ezm_460mm should match only ezm_pub
    out = relevant_cohorts_for_profile(
        project_path=tmp_path, profile_id="ezm_460mm",
    )
    assert out == ["ezm_pub"]
    # tamco_black_bucket should match nor_pub (and any other NOR/NOF/OF cohort)
    out_tamco = relevant_cohorts_for_profile(
        project_path=tmp_path, profile_id="tamco_black_bucket",
    )
    assert "nor_pub" in out_tamco
    assert "ezm_pub" not in out_tamco
    # rr_pub never matches an arena profile
    assert "rr_pub" not in out_tamco


def test_relevant_cohorts_handles_unparseable_cohort_files(tmp_path: Path):
    cohorts_dir = tmp_path / "cohorts"
    cohorts_dir.mkdir()
    (cohorts_dir / "broken.json").write_text("not json")
    (cohorts_dir / "valid.json").write_text(json.dumps({
        "name": "valid", "task_types": ["EZM"], "members": [],
    }))
    out = relevant_cohorts_for_profile(
        project_path=tmp_path, profile_id="ezm_460mm",
    )
    assert out == ["valid"]


def test_run_kind_slug_pinned():
    """T17 invariant: external code keys on this slug. Changes must be
    deliberate and coordinated with the Training Monitor pane."""
    assert RUN_KIND_SLUG == "arena_inference"
    assert RUN_ARTIFACT_KIND == "arena_inference_run_dir"
