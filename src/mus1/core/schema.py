"""
Database schema definitions for MUS1 SQLite backend.

This module defines SQLAlchemy models that map to the clean domain models
in metadata.py. These are the actual database tables.
"""

import json
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from typing import List
from .metadata import Sex, ProcessingStage, InheritancePattern, WorkerProvider, ScanTargetKind

Base = declarative_base()

# ===========================================
# DATABASE MODELS (SQLAlchemy)
# ===========================================

class SubjectModel(Base):
    """Database model for subjects."""
    __tablename__ = 'subjects'

    id = Column(String, primary_key=True)
    sex = Column(SQLEnum(Sex), nullable=False)
    birth_date = Column(DateTime, nullable=True)
    death_date = Column(DateTime, nullable=True)
    genotype = Column(String, nullable=True)
    treatment = Column(String, nullable=True)
    notes = Column(Text, default="")
    date_added = Column(DateTime, nullable=False)

    # Relationships
    experiments = relationship("ExperimentModel", back_populates="subject")

class ExperimentModel(Base):
    """Database model for experiments."""
    __tablename__ = 'experiments'

    id = Column(String, primary_key=True)
    subject_id = Column(String, ForeignKey('subjects.id'), nullable=False)
    experiment_type = Column(String, nullable=False)
    date_recorded = Column(DateTime, nullable=False)
    processing_stage = Column(SQLEnum(ProcessingStage), nullable=False)
    experiment_subtype = Column(String, nullable=True)
    notes = Column(Text, default="")
    date_added = Column(DateTime, nullable=False)

    # Relationships
    subject = relationship("SubjectModel", back_populates="experiments")
    videos = relationship("VideoModel", secondary="experiment_videos")

class VideoModel(Base):
    """Database model for video files."""
    __tablename__ = 'videos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String, nullable=False, unique=True)
    hash = Column(String, nullable=False, index=True)
    recorded_time = Column(DateTime, nullable=True)
    size_bytes = Column(Integer, default=0)
    last_modified = Column(Float, default=0.0)
    date_added = Column(DateTime, nullable=False)

# Association table for experiment-video many-to-many relationship
experiment_videos = Base.metadata.tables.get('experiment_videos', None)
if experiment_videos is None:
    from sqlalchemy import Table
    experiment_videos = Table('experiment_videos', Base.metadata,
        Column('experiment_id', String, ForeignKey('experiments.id')),
        Column('video_id', Integer, ForeignKey('videos.id'))
    )

class WorkerModel(Base):
    """Database model for workers."""
    __tablename__ = 'workers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    ssh_alias = Column(String, nullable=False)
    role = Column(String, nullable=True)
    provider = Column(SQLEnum(WorkerProvider), nullable=False)
    os_type = Column(String, nullable=True)

class ScanTargetModel(Base):
    """Database model for scan targets."""
    __tablename__ = 'scan_targets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    kind = Column(SQLEnum(ScanTargetKind), nullable=False)
    roots = Column(Text, nullable=False)  # JSON-encoded list of paths
    ssh_alias = Column(String, nullable=True)

class ProjectModel(Base):
    """Database model for project configuration."""
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    shared_root = Column(String, nullable=True)
    lab_id = Column(String, nullable=True)
    settings = Column(Text, default="{}")  # JSON-encoded settings
    date_created = Column(DateTime, nullable=False)

class PluginMetadataModel(Base):
    """Database model for plugin metadata."""
    __tablename__ = 'plugin_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    version = Column(String, nullable=False)
    description = Column(Text, default="")
    author = Column(String, nullable=False)
    date_created = Column(DateTime, nullable=False)

class PluginResultModel(Base):
    """Database model for plugin analysis results."""
    __tablename__ = 'plugin_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(String, ForeignKey('experiments.id'), nullable=False)
    plugin_name = Column(String, nullable=False)
    capability = Column(String, nullable=False)
    result_data = Column(Text, nullable=False)  # JSON-encoded result data
    status = Column(String, nullable=False)  # 'success', 'failed', 'running'
    error_message = Column(Text, default="")
    output_files = Column(Text, default="{}")  # JSON-encoded list of output file paths
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

# ===========================================
# DATABASE UTILITIES
# ===========================================

class Database:
    """Database connection and session management."""

    def __init__(self, db_path: str):
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self):
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)

    def get_session(self):
        """Get a database session."""
        return self.SessionLocal()

    def drop_tables(self):
        """Drop all tables (for testing)."""
        Base.metadata.drop_all(bind=self.engine)

# ===========================================
# DATA MAPPING FUNCTIONS
# ===========================================

def subject_to_model(subject) -> SubjectModel:
    """Convert domain Subject to database model."""
    return SubjectModel(
        id=subject.id,
        sex=subject.sex,
        birth_date=subject.birth_date,
        death_date=subject.death_date,
        genotype=subject.genotype,
        treatment=subject.treatment,
        notes=subject.notes,
        date_added=subject.date_added
    )

def model_to_subject(model) -> 'Subject':
    """Convert database model to domain Subject."""
    from .metadata import Subject
    return Subject(
        id=model.id,
        sex=model.sex,
        birth_date=model.birth_date,
        death_date=model.death_date,
        genotype=model.genotype,
        treatment=model.treatment,
        notes=model.notes,
        date_added=model.date_added
    )

def experiment_to_model(experiment) -> ExperimentModel:
    """Convert domain Experiment to database model."""
    return ExperimentModel(
        id=experiment.id,
        subject_id=experiment.subject_id,
        experiment_type=experiment.experiment_type,
        date_recorded=experiment.date_recorded,
        processing_stage=experiment.processing_stage,
        experiment_subtype=experiment.experiment_subtype,
        notes=experiment.notes,
        date_added=experiment.date_added
    )

def model_to_experiment(model) -> 'Experiment':
    """Convert database model to domain Experiment."""
    from .metadata import Experiment
    return Experiment(
        id=model.id,
        subject_id=model.subject_id,
        experiment_type=model.experiment_type,
        date_recorded=model.date_recorded,
        processing_stage=model.processing_stage,
        experiment_subtype=model.experiment_subtype,
        notes=model.notes,
        date_added=model.date_added
    )

def plugin_metadata_to_model(metadata) -> PluginMetadataModel:
    """Convert domain PluginMetadata to database model."""
    return PluginMetadataModel(
        name=metadata.name,
        version=metadata.version,
        description=metadata.description,
        author=metadata.author,
        date_created=metadata.date_created
    )

def model_to_plugin_metadata(model) -> 'PluginMetadata':
    """Convert database model to domain PluginMetadata."""
    from .metadata import PluginMetadata
    return PluginMetadata(
        name=model.name,
        date_created=model.date_created,
        version=model.version,
        description=model.description,
        author=model.author
    )

def plugin_result_to_model(result) -> PluginResultModel:
    """Convert domain PluginResult to database model."""
    return PluginResultModel(
        experiment_id=result.experiment_id,
        plugin_name=result.plugin_name,
        capability=result.capability,
        result_data=json.dumps(result.result_data),
        status=result.status,
        error_message=result.error_message,
        output_files=json.dumps(result.output_files),
        created_at=result.created_at,
        completed_at=result.completed_at
    )

def model_to_plugin_result(model) -> 'PluginResult':
    """Convert database model to domain PluginResult."""
    from .metadata import PluginResult
    return PluginResult(
        experiment_id=model.experiment_id,
        plugin_name=model.plugin_name,
        capability=model.capability,
        result_data=json.loads(model.result_data) if model.result_data else {},
        status=model.status,
        error_message=model.error_message,
        output_files=json.loads(model.output_files) if model.output_files else [],
        created_at=model.created_at,
        completed_at=model.completed_at
    )
