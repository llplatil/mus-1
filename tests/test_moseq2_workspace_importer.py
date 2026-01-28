"""
Smoke test for MoSeq2 workspace importer.
"""

import tempfile
import shutil
from pathlib import Path
import pandas as pd

from mus1.core.schema import Database
from mus1.core.repository import get_repository_factory
from mus1.core.importers.moseq2_workspace import import_session_index


def test_import_smoke():
    """Minimal smoke test for moseq2-workspace importer."""
    # Create temporary directories
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create project directory with database
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        db_path = project_path / "mus1.db"
        db = Database(str(db_path))
        db.create_tables()
        repos = get_repository_factory(db)
        
        # Create workspace directory
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        
        # Create a minimal CSV file
        csv_path = workspace_root / "session_index.csv"
        test_data = {
            "session_id": ["OF__262__2024-10-09"],
            "task": ["OF"],
            "subject_id": ["262"],
            "recording_date": ["2024-10-09"],
            "birthdate": ["2024-03-11"],
            "age_days": [212],
            "sex": ["M"],
            "genotype": ["HET"],
            "treatment": ["CONTROL"],
            "arena_bucket": ["OLD"],
            "video_path": [""],
            "moseq2_results_h5_path": ["/some/path/results.h5"],
        }
        df = pd.DataFrame(test_data)
        df.to_csv(csv_path, index=False)
        
        # Run import
        stats = import_session_index(
            repos,
            workspace_root=workspace_root,
            session_index_csv=csv_path,
            check_paths_exist=False,  # Don't check paths for smoke test
        )
        
        # Verify basic stats
        assert stats.rows_total == 1
        assert stats.subjects_upserted == 1
        assert stats.experiments_upserted == 1
        
        # Verify subject was created
        subject = repos.subjects.find_by_id("262")
        assert subject is not None
        assert subject.id == "262"
        
        # Verify experiment was created
        experiment = repos.experiments.find_by_id("OF__262__2024-10-09")
        assert experiment is not None
        assert experiment.subject_id == "262"
        assert experiment.experiment_type == "OF"


if __name__ == "__main__":
    test_import_smoke()
    print("✓ Smoke test passed")
