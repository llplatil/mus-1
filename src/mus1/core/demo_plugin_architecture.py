"""
Demo script showing the clean plugin architecture in action.

This demonstrates:
1. Plugin registration and discovery
2. Clean data access through PluginService
3. Analysis execution with proper result storage
4. Integration with SQLite backend
"""

from datetime import datetime
from pathlib import Path
import tempfile
import os

from .plugin_manager_clean import PluginManagerClean, PluginService
from .schema import Database
from .metadata import Subject, Experiment, Sex, ProcessingStage, ProjectConfig
from .repository import RepositoryFactory
from ..plugins.base_plugin import BasePlugin


class DemoAnalysisPlugin(BasePlugin):
    """Demo plugin showing clean architecture integration."""

    def validate_experiment(self, experiment, project_config):
        """Validate experiment for this plugin."""
        if experiment.experiment_type not in ["OpenField", "NOR"]:
            raise ValueError(f"Plugin supports OpenField and NOR, got {experiment.experiment_type}")
        print(f"✓ Experiment {experiment.id} validated for analysis")

    def analyze_experiment(self, experiment, plugin_service, capability, project_config):
        """Execute analysis using clean architecture data access."""
        print(f"🔬 Executing {capability} analysis on experiment {experiment.id}")

        # Get experiment data using PluginService
        exp_data = plugin_service.get_experiment_data(experiment.id)
        if not exp_data:
            return {
                'status': 'failed',
                'error': f'Could not load data for experiment {experiment.id}',
                'capability_executed': capability
            }

        subject = exp_data['subject']
        print(f"📊 Subject: {subject.id} ({subject.sex.value}, {subject.genotype})")

        # Simulate analysis based on capability
        if capability == "basic_metrics":
            result_data = {
                'total_frames': 18000,  # 10 minutes at 30fps
                'duration_seconds': 600,
                'center_time_percent': 35.2,
                'distance_traveled_cm': 1250.5
            }
        elif capability == "zone_analysis":
            result_data = {
                'center_zone_time_percent': 35.2,
                'peripheral_zone_time_percent': 64.8,
                'zone_transitions': 45
            }
        else:
            result_data = {'custom_metric': 42}

        print(f"✅ Analysis completed: {result_data}")

        return {
            'status': 'success',
            'capability_executed': capability,
            'result_data': result_data,
            'message': f'Successfully analyzed {capability} for experiment {experiment.id}',
            'output_file_paths': [f'/tmp/analysis_{experiment.id}_{capability}.json']
        }

    def plugin_self_metadata(self):
        from .metadata import PluginMetadata
        return PluginMetadata(
            name="demo_analysis_plugin",
            date_created=datetime.now(),
            version="1.0.0",
            description="Demo plugin showing clean architecture integration",
            author="MUS1 Team",
            supported_experiment_types=["OpenField", "NOR"]
        )

    def readable_data_formats(self):
        return ["csv", "h5", "json"]

    def analysis_capabilities(self):
        return ["basic_metrics", "zone_analysis", "custom_analysis"]


def demo_plugin_architecture():
    """Demonstrate the complete plugin architecture."""
    print("🚀 MUS1 Clean Plugin Architecture Demo")
    print("=" * 50)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        # Initialize database and create tables
        print("📝 Initializing SQLite database...")
        db = Database(db_path)
        db.create_tables()

        # Initialize repositories and create test data
        repos = RepositoryFactory(db)
        print("📊 Creating test subjects and experiments...")

        # Create subjects
        subject1 = repos.subjects.save(Subject(
            id="SUB001",
            sex=Sex.MALE,
            genotype="ATP7B:WT",
            birth_date=datetime(2023, 6, 15),
            notes="Test subject for plugin demo",
            date_added=datetime.now()
        ))

        subject2 = repos.subjects.save(Subject(
            id="SUB002",
            sex=Sex.FEMALE,
            genotype="ATP7B:KO",
            birth_date=datetime(2023, 6, 16),
            notes="Second test subject",
            date_added=datetime.now()
        ))

        # Create experiments
        experiment1 = repos.experiments.save(Experiment(
            id="EXP001",
            subject_id="SUB001",
            experiment_type="OpenField",
            date_recorded=datetime(2024, 1, 15, 10, 0),
            processing_stage=ProcessingStage.RECORDED,
            notes="Open field test for anxiety-like behavior",
            date_added=datetime.now()
        ))

        experiment2 = repos.experiments.save(Experiment(
            id="EXP002",
            subject_id="SUB002",
            experiment_type="NOR",
            date_recorded=datetime(2024, 1, 16, 14, 30),
            processing_stage=ProcessingStage.TRACKED,
            notes="Novel object recognition test",
            date_added=datetime.now()
        ))

        print(f"✓ Created {len(repos.subjects.find_all())} subjects")
        print(f"✓ Created {len(repos.experiments.find_all())} experiments")

        # Initialize plugin system
        print("\n🔌 Initializing plugin system...")
        plugin_manager = PluginManagerClean(db)
        plugin_service = PluginService(db)

        # Register demo plugin
        demo_plugin = DemoAnalysisPlugin()
        plugin_manager.register_plugin(demo_plugin)
        print(f"✓ Registered plugin: {demo_plugin.plugin_self_metadata().name}")

        # Test plugin discovery
        print("\n🔍 Testing plugin discovery...")
        all_plugins = plugin_manager.get_all_plugins()
        print(f"✓ Found {len(all_plugins)} registered plugins")

        # Test capability discovery
        basic_plugins = plugin_manager.get_plugins_with_capability("basic_metrics")
        print(f"✓ Found {len(basic_plugins)} plugins for 'basic_metrics' capability")

        zone_plugins = plugin_manager.get_plugins_with_capability("zone_analysis")
        print(f"✓ Found {len(zone_plugins)} plugins for 'zone_analysis' capability")

        # Test supported types
        supported_types = plugin_manager.get_supported_experiment_types()
        print(f"✓ Supported experiment types: {supported_types}")

        # Execute analysis
        print("\n⚡ Executing plugin analysis...")

        # Test 1: Basic metrics analysis
        print("\n📈 Running basic_metrics analysis on EXP001...")
        result1 = plugin_manager.run_plugin_analysis(
            experiment_id="EXP001",
            plugin_name="demo_analysis_plugin",
            capability="basic_metrics",
            project_config=ProjectConfig(name="demo_project")
        )
        print(f"Result: {result1['status']}")
        if result1['status'] == 'success':
            print(f"Metrics: {result1['result_data']}")

        # Test 2: Zone analysis
        print("\n📊 Running zone_analysis on EXP002...")
        result2 = plugin_manager.run_plugin_analysis(
            experiment_id="EXP002",
            plugin_name="demo_analysis_plugin",
            capability="zone_analysis",
            project_config=ProjectConfig(name="demo_project")
        )
        print(f"Result: {result2['status']}")
        if result2['status'] == 'success':
            print(f"Zone data: {result2['result_data']}")

        # Test 3: Invalid experiment
        print("\n❌ Testing error handling with invalid experiment...")
        result3 = plugin_manager.run_plugin_analysis(
            experiment_id="INVALID_EXP",
            plugin_name="demo_analysis_plugin",
            capability="basic_metrics",
            project_config=ProjectConfig(name="demo_project")
        )
        print(f"Result: {result3['status']} - {result3.get('error', 'No error message')}")

        # Verify results stored in database
        print("\n💾 Verifying analysis results stored in database...")
        stored_result = plugin_service.get_analysis_result(
            "EXP001", "demo_analysis_plugin", "basic_metrics"
        )
        if stored_result:
            print("✓ Analysis result successfully stored in database")
            print(f"  Status: {stored_result.status}")
            print(f"  Data: {stored_result.result_data}")
        else:
            print("✗ Analysis result not found in database")

        # Show plugin metadata storage
        print("\n📋 Plugin metadata in database:")
        with db.get_session() as session:
            from .schema import PluginMetadataModel
            metadata_records = session.query(PluginMetadataModel).all()
            for record in metadata_records:
                print(f"✓ Plugin: {record.name} v{record.version}")

        print("\n" + "=" * 50)
        print("✅ Clean Plugin Architecture Demo Completed Successfully!")
        print("\nKey Features Demonstrated:")
        print("• Plugin registration and metadata storage")
        print("• Clean data access through PluginService")
        print("• Repository pattern integration")
        print("• Analysis result persistence")
        print("• Error handling and validation")
        print("• SQLite backend integration")

    finally:
        # Clean up temporary database
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    demo_plugin_architecture()
