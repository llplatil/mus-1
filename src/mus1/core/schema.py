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
from .metadata import Sex, ProcessingStage, SubjectDesignation, InheritancePattern, WorkerProvider, ScanTargetKind

Base = declarative_base()

# ===========================================
# DATABASE MODELS (SQLAlchemy)
# ===========================================

class ColonyModel(Base):
    """Database model for colonies."""
    __tablename__ = 'colonies'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    lab_id = Column(String, nullable=False)
    genotype_of_interest = Column(String, nullable=True)
    background_strain = Column(String, nullable=True)
    common_traits = Column(Text, default="{}")  # JSON-encoded dict
    notes = Column(Text, default="")
    date_added = Column(DateTime, nullable=False)

    # Relationships
    subjects = relationship("SubjectModel", back_populates="colony")

class SubjectModel(Base):
    """Database model for subjects."""
    __tablename__ = 'subjects'

    id = Column(String, primary_key=True)
    colony_id = Column(String, ForeignKey('colonies.id'), nullable=False)
    sex = Column(SQLEnum(Sex), nullable=False)
    designation = Column(SQLEnum(SubjectDesignation), nullable=True)
    birth_date = Column(DateTime, nullable=True)
    death_date = Column(DateTime, nullable=True)
    individual_genotype = Column(String, nullable=True)
    individual_treatment = Column(String, nullable=True)
    notes = Column(Text, default="")
    date_added = Column(DateTime, nullable=False)

    # Relationships
    colony = relationship("ColonyModel", back_populates="subjects")
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

class UserModel(Base):
    """Database model for users."""
    __tablename__ = 'users'

    id = Column(String, primary_key=True)  # User key/identifier
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    organization = Column(String, nullable=True)
    default_projects_dir = Column(String, nullable=True)
    default_shared_dir = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    labs = relationship("LabModel", back_populates="creator")

class LabModel(Base):
    """Database model for labs."""
    __tablename__ = 'labs'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    institution = Column(String, nullable=True)
    pi_name = Column(String, nullable=True)
    creator_id = Column(String, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, nullable=False)

    # Relationships
    creator = relationship("UserModel", back_populates="labs")
    projects = relationship("LabProjectModel", back_populates="lab")

class LabProjectModel(Base):
    """Database model for lab-project associations."""
    __tablename__ = 'lab_projects'

    id = Column(Integer, primary_key=True, autoincrement=True)
    lab_id = Column(String, ForeignKey('labs.id'), nullable=False)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    created_date = Column(DateTime, nullable=False)

    # Relationships
    lab = relationship("LabModel", back_populates="projects")

class LabMemberModel(Base):
    """Database model for lab membership (user belongs to lab)."""
    __tablename__ = 'lab_members'

    lab_id = Column(String, ForeignKey('labs.id'), primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), primary_key=True)
    role = Column(String, default="member")
    joined_at = Column(DateTime, nullable=False)

class LabWorkerModel(Base):
    """Association between labs and workers (many-to-many)."""
    __tablename__ = 'lab_workers'

    lab_id = Column(String, ForeignKey('labs.id'), primary_key=True)
    worker_id = Column(Integer, ForeignKey('workers.id'), primary_key=True)
    permissions = Column(String, nullable=True)
    tags = Column(Text, default="[]")  # JSON-encoded list of tags

class LabScanTargetModel(Base):
    """Association between labs and scan targets (many-to-many)."""
    __tablename__ = 'lab_scan_targets'

    lab_id = Column(String, ForeignKey('labs.id'), primary_key=True)
    scan_target_id = Column(Integer, ForeignKey('scan_targets.id'), primary_key=True)

class WorkgroupModel(Base):
    """Database model for workgroups."""
    __tablename__ = 'workgroups'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    share_key_hash = Column(String, nullable=False)  # Salted hash of shareable key
    created_at = Column(DateTime, nullable=False)

    # Relationships
    members = relationship("WorkgroupMemberModel", back_populates="workgroup")

class WorkgroupMemberModel(Base):
    """Database model for workgroup membership."""
    __tablename__ = 'workgroup_members'

    id = Column(Integer, primary_key=True, autoincrement=True)
    workgroup_id = Column(String, ForeignKey('workgroups.id'), nullable=False)
    member_email = Column(String, nullable=False)
    role = Column(String, default="member")  # 'admin', 'member', etc.
    added_at = Column(DateTime, nullable=False)

    # Relationships
    workgroup = relationship("WorkgroupModel", back_populates="members")

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

def colony_to_model(colony) -> ColonyModel:
    """Convert domain Colony to database model."""
    return ColonyModel(
        id=colony.id,
        name=colony.name,
        lab_id=colony.lab_id,
        genotype_of_interest=colony.genotype_of_interest,
        background_strain=colony.background_strain,
        common_traits=json.dumps(colony.common_traits),
        notes=colony.notes,
        date_added=colony.date_added
    )

def model_to_colony(model) -> 'Colony':
    """Convert database model to domain Colony."""
    from .metadata import Colony
    return Colony(
        id=model.id,
        name=model.name,
        lab_id=model.lab_id,
        genotype_of_interest=model.genotype_of_interest,
        background_strain=model.background_strain,
        common_traits=json.loads(model.common_traits) if model.common_traits else {},
        notes=model.notes,
        date_added=model.date_added
    )

def subject_to_model(subject) -> SubjectModel:
    """Convert domain Subject to database model."""
    return SubjectModel(
        id=subject.id,
        colony_id=subject.colony_id,
        sex=subject.sex,
        designation=subject.designation,
        birth_date=subject.birth_date,
        death_date=subject.death_date,
        individual_genotype=subject.individual_genotype,
        individual_treatment=subject.individual_treatment,
        notes=subject.notes,
        date_added=subject.date_added
    )

def model_to_subject(model) -> 'Subject':
    """Convert database model to domain Subject."""
    from .metadata import Subject, SubjectDesignation
    return Subject(
        id=model.id,
        colony_id=model.colony_id,
        sex=model.sex,
        designation=model.designation or SubjectDesignation.EXPERIMENTAL,  # Default for legacy databases
        birth_date=model.birth_date,
        death_date=model.death_date,
        individual_genotype=model.individual_genotype,
        individual_treatment=model.individual_treatment,
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

# ===========================================
# USER AND LAB MAPPING FUNCTIONS
# ===========================================

def user_to_model(user) -> UserModel:
    """Convert domain User to database model."""
    return UserModel(
        id=user.id,
        name=user.name,
        email=user.email,
        organization=user.organization,
        default_projects_dir=str(user.default_projects_dir) if user.default_projects_dir else None,
        default_shared_dir=str(user.default_shared_dir) if user.default_shared_dir else None,
        created_at=user.created_at,
        updated_at=user.updated_at
    )

def model_to_user(model) -> 'User':
    """Convert database model to domain User."""
    from .metadata import User
    from pathlib import Path
    return User(
        id=model.id,
        name=model.name,
        email=model.email,
        organization=model.organization,
        default_projects_dir=Path(model.default_projects_dir) if model.default_projects_dir else None,
        default_shared_dir=Path(model.default_shared_dir) if model.default_shared_dir else None,
        created_at=model.created_at,
        updated_at=model.updated_at
    )

def lab_to_model(lab) -> LabModel:
    """Convert domain Lab to database model."""
    return LabModel(
        id=lab.id,
        name=lab.name,
        institution=lab.institution,
        pi_name=lab.pi_name,
        creator_id=lab.creator_id,
        created_at=lab.created_at
    )

def model_to_lab(model) -> 'Lab':
    """Convert database model to domain Lab."""
    from .metadata import Lab
    return Lab(
        id=model.id,
        name=model.name,
        institution=model.institution,
        pi_name=model.pi_name,
        creator_id=model.creator_id,
        created_at=model.created_at
    )

def workgroup_to_model(workgroup) -> WorkgroupModel:
    """Convert domain Workgroup to database model."""
    return WorkgroupModel(
        id=workgroup.id,
        name=workgroup.name,
        share_key_hash=workgroup.share_key_hash,
        created_at=workgroup.created_at
    )

def model_to_workgroup(model) -> 'Workgroup':
    """Convert database model to domain Workgroup."""
    from .metadata import Workgroup
    return Workgroup(
        id=model.id,
        name=model.name,
        share_key_hash=model.share_key_hash,
        created_at=model.created_at
    )
