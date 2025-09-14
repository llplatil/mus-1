"""
Demo of the clean MUS1 architecture.

This demonstrates the complete flow:
1. CLI command
2. DTO validation
3. Domain model creation
4. Repository layer
5. SQLite database persistence
6. Clean data retrieval
"""

from pathlib import Path
from datetime import datetime
import tempfile
import json

from .metadata import Subject, Experiment, VideoFile, Worker, ScanTarget, Sex, ProcessingStage, WorkerProvider, ScanTargetKind
from .project_manager_clean import ProjectManagerClean
from .simple_cli import app  # Import CLI for demonstration

def demo_clean_architecture():
    """Demonstrate the clean architecture end-to-end."""

    print("🎯 MUS1 Clean Architecture Demo")
    print("=" * 50)

    # Create temporary project directory
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir) / "demo_project"
        project_path.mkdir()

        print(f"📁 Created demo project at: {project_path}")

        # Initialize project manager (this creates the database)
        pm = ProjectManagerClean(project_path)
        print("🗄️  Initialized SQLite database")

        # 1. Add subjects
        print("\n👤 Adding subjects...")
        subject1 = Subject(
            id="SUB001",
            sex=Sex.MALE,
            genotype="ATP7B:WT",
            birth_date=datetime(2023, 1, 15),
            notes="Wild-type male subject"
        )

        subject2 = Subject(
            id="SUB002",
            sex=Sex.FEMALE,
            genotype="ATP7B:KO",
            birth_date=datetime(2023, 2, 20),
            notes="Knockout female subject"
        )

        saved_subject1 = pm.add_subject(subject1)
        saved_subject2 = pm.add_subject(subject2)

        print(f"✅ Added subject: {saved_subject1.id} ({saved_subject1.genotype}) - Age: {saved_subject1.age_days} days")
        print(f"✅ Added subject: {saved_subject2.id} ({saved_subject2.genotype}) - Age: {saved_subject2.age_days} days")

        # 2. Add experiments
        print("\n🧪 Adding experiments...")
        experiment1 = Experiment(
            id="EXP001",
            subject_id="SUB001",
            experiment_type="OpenField",
            date_recorded=datetime(2024, 3, 1, 10, 30),
            processing_stage=ProcessingStage.RECORDED,
            experiment_subtype="familiarization",
            notes="First OpenField trial"
        )

        experiment2 = Experiment(
            id="EXP002",
            subject_id="SUB002",
            experiment_type="NOR",
            date_recorded=datetime(2024, 3, 2, 14, 15),
            processing_stage=ProcessingStage.TRACKED,
            notes="Novel Object Recognition test"
        )

        saved_exp1 = pm.add_experiment(experiment1)
        saved_exp2 = pm.add_experiment(experiment2)

        print(f"✅ Added experiment: {saved_exp1.id} ({saved_exp1.experiment_type}) - Ready for analysis: {saved_exp1.is_ready_for_analysis}")
        print(f"✅ Added experiment: {saved_exp2.id} ({saved_exp2.experiment_type}) - Ready for analysis: {saved_exp2.is_ready_for_analysis}")

        # 3. Add video files
        print("\n🎥 Adding video files...")
        video1 = VideoFile(
            path=Path("/data/videos/sub001_openfield_001.mp4"),
            hash="abc123def456",
            recorded_time=datetime(2024, 3, 1, 10, 30),
            size_bytes=1024000000,  # 1GB
            last_modified=1709290200.0
        )

        saved_video1 = pm.add_video(video1)
        print(f"✅ Added video: {saved_video1.path.name} (hash: {saved_video1.hash[:8]}...)")

        # 4. Add workers
        print("\n👷 Adding workers...")
        worker1 = Worker(
            name="compute-node-01",
            ssh_alias="server1",
            role="compute",
            provider=WorkerProvider.SSH,
            os_type="linux"
        )

        saved_worker1 = pm.add_worker(worker1)
        print(f"✅ Added worker: {saved_worker1.name} ({saved_worker1.provider.value})")

        # 5. Add scan targets
        print("\n🎯 Adding scan targets...")
        target1 = ScanTarget(
            name="lab-server-data",
            kind=ScanTargetKind.SSH,
            roots=[Path("/mnt/data/videos"), Path("/mnt/data/behavior")],
            ssh_alias="lab-server"
        )

        saved_target1 = pm.add_scan_target(target1)
        print(f"✅ Added scan target: {saved_target1.name} ({saved_target1.kind.value})")

        # 6. Demonstrate data retrieval
        print("\n📊 Data retrieval demonstration:")

        # Get all subjects
        subjects = pm.list_subjects()
        print(f"📋 Total subjects: {len(subjects)}")
        for subj in subjects:
            exp_count = len(pm.list_experiments_for_subject(subj.id))
            print(f"   • {subj.id}: {subj.genotype}, {exp_count} experiments")

        # Get all experiments
        experiments = pm.list_experiments()
        print(f"📋 Total experiments: {len(experiments)}")
        for exp in experiments:
            print(f"   • {exp.id}: {exp.experiment_type} for {exp.subject_id}")

        # Get project stats
        stats = pm.get_stats()
        print("\n📈 Project Statistics:")
        for key, value in stats.items():
            print(f"   • {key}: {value}")

        # 7. Demonstrate duplicate detection
        print("\n🔍 Duplicate video detection:")
        duplicates = pm.find_duplicate_videos()
        if duplicates:
            print(f"⚠️  Found {len(duplicates)} duplicate groups")
            for dup in duplicates:
                print(f"   • Hash {dup['hash'][:8]}...: {dup['count']} copies")
        else:
            print("✅ No duplicate videos found")

        print("\n🎉 Clean Architecture Demo Complete!")
        print("\nKey Benefits Demonstrated:")
        print("✅ Clean separation: Domain ↔ DTO ↔ Database")
        print("✅ Simple, focused classes with single responsibilities")
        print("✅ SQLite backend with proper relationships")
        print("✅ Easy to extend and maintain")
        print("✅ No complex inheritance or mixins")
        print("✅ Clear data flow and validation")

        # Show database contents
        db_path = project_path / "mus1.db"
        if db_path.exists():
            print(f"\n💾 SQLite database created at: {db_path}")
            print(f"   Size: {db_path.stat().st_size} bytes")

        # Show project config
        config_path = project_path / "project.json"
        if config_path.exists():
            print(f"\n⚙️  Project config created at: {config_path}")
            with open(config_path) as f:
                config = json.load(f)
            print(f"   Project: {config['name']}")
            print(f"   Created: {config['date_created']}")

if __name__ == "__main__":
    demo_clean_architecture()
