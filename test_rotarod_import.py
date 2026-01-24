#!/usr/bin/env python3
"""Smoke test script for rotarod import functionality."""

import sys
import tempfile
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mus1.core.schema import Database
from mus1.core.repository import get_repository_factory
from mus1.core.importers.rotarod import import_rotarod_csv

CSV_PATH = Path("/center1/WDMOSEQ2/llplatil/WDMOSEQ2/moseq2_workspace/statistics_summaries/rotarod_reanalysis/rotarod_attempts_long_cleaned.csv")


def main():
    """Run smoke test."""
    print("=" * 60)
    print("Rotarod Import Smoke Test")
    print("=" * 60)
    
    # Create temporary project directory
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir) / "test_project"
        project_path.mkdir()
        db_path = project_path / "mus1.db"
        
        print(f"\n[1] Creating test database at: {db_path}")
        db = Database(str(db_path))
        db.create_tables()
        print("    ✓ Database created")
        
        print(f"\n[2] Initializing repositories")
        repos = get_repository_factory(db)
        print("    ✓ Repositories initialized")
        
        print(f"\n[3] Importing rotarod CSV: {CSV_PATH}")
        if not CSV_PATH.exists():
            print(f"    ✗ CSV file not found: {CSV_PATH}")
            return 1
        
        try:
            stats = import_rotarod_csv(
                repos,
                csv_path=CSV_PATH,
                assay_type="rotarod",
            )
            
            print("    ✓ Import completed")
            print(f"\n[4] Import Statistics:")
            print(f"    - Rows processed: {stats.rows_total}")
            print(f"    - Assay sessions created: {stats.assay_sessions_created}")
            print(f"    - Assay measurements created: {stats.assay_measurements_created}")
            print(f"    - Subjects created: {stats.subjects_created}")
            print(f"    - Subjects skipped: {stats.subjects_skipped}")
            print(f"    - Errors: {stats.errors}")
            
            # Verify some data was imported
            print(f"\n[5] Verification:")
            all_subjects = repos.subjects.find_all()
            print(f"    - Total subjects in DB: {len(all_subjects)}")
            
            # Check assay sessions
            from mus1.core.schema import AssaySessionModel
            with db.get_session() as session:
                session_count = session.query(AssaySessionModel).count()
                print(f"    - Assay sessions in DB: {session_count}")
                
                from mus1.core.schema import AssayMeasurementModel
                measurement_count = session.query(AssayMeasurementModel).count()
                print(f"    - Assay measurements in DB: {measurement_count}")
            
            # Check a sample session
            print(f"\n[6] Sample Data Check:")
            with db.get_session() as session:
                sample_session = session.query(AssaySessionModel).first()
                if sample_session:
                    print(f"    - Sample session ID: {sample_session.id}")
                    print(f"    - Assay type: {sample_session.assay_type}")
                    print(f"    - Subject ID: {sample_session.subject_id}")
                    print(f"    - Occurred at: {sample_session.occurred_at}")
                    
                    sample_measurements = session.query(AssayMeasurementModel).filter(
                        AssayMeasurementModel.assay_session_id == sample_session.id
                    ).limit(3).all()
                    print(f"    - Sample measurements: {len(sample_measurements)}")
                    for m in sample_measurements:
                        print(f"      * {m.metric}: {m.value} {m.units or ''}")
                        if m.qc_flags_json:
                            import json
                            qc_flags = json.loads(m.qc_flags_json)
                            if qc_flags:
                                print(f"        QC flags: {qc_flags}")
            
            print(f"\n[7] Test Results:")
            if stats.errors == 0 and stats.assay_sessions_created > 0:
                print("    ✓ All checks passed!")
                return 0
            else:
                print("    ⚠ Some issues detected (check stats above)")
                return 1
                
        except Exception as e:
            print(f"    ✗ Import failed with error: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
