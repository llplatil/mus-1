"""
Repository layer for clean data access patterns.

This provides a clean abstraction over the SQLite database for domain operations.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
from sqlalchemy.orm import Session
from .metadata import Subject, Experiment, VideoFile, Worker, ScanTarget
from .schema import (
    Database, SubjectModel, ExperimentModel, VideoModel,
    WorkerModel, ScanTargetModel, ProjectModel, ColonyModel,
    subject_to_model, model_to_subject,
    experiment_to_model, model_to_experiment,
    colony_to_model, model_to_colony
)

class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, db: Database):
        self.db = db

    def _get_session(self) -> Session:
        """Get database session."""
        return self.db.get_session()

class ColonyRepository(BaseRepository):
    """Repository for colony operations."""

    def save(self, colony) -> 'Colony':
        """Save a colony."""
        from .metadata import Colony
        db_colony = colony_to_model(colony)
        with self._get_session() as session:
            merged = session.merge(db_colony)  # merge handles both insert and update
            session.commit()
            return model_to_colony(merged)

    def find_by_id(self, colony_id: str) -> Optional['Colony']:
        """Find colony by ID."""
        with self._get_session() as session:
            db_colony = session.query(ColonyModel).filter(
                ColonyModel.id == colony_id
            ).first()
            return model_to_colony(db_colony) if db_colony else None

    def find_by_lab(self, lab_id: str) -> List['Colony']:
        """Find colonies by lab ID."""
        with self._get_session() as session:
            db_colonies = session.query(ColonyModel).filter(
                ColonyModel.lab_id == lab_id
            ).all()
            return [model_to_colony(db_colony) for db_colony in db_colonies]

    def find_all(self) -> List['Colony']:
        """Find all colonies."""
        with self._get_session() as session:
            db_colonies = session.query(ColonyModel).all()
            return [model_to_colony(db_colony) for db_colony in db_colonies]

    def delete(self, colony_id: str) -> bool:
        """Delete colony by ID."""
        with self._get_session() as session:
            # Check if colony has subjects
            subject_count = session.query(SubjectModel).filter(
                SubjectModel.colony_id == colony_id
            ).count()
            if subject_count > 0:
                return False  # Cannot delete colony with subjects

            result = session.query(ColonyModel).filter(
                ColonyModel.id == colony_id
            ).delete()
            session.commit()
            return result > 0

class SubjectRepository(BaseRepository):
    """Repository for subject operations."""

    def save(self, subject: Subject) -> Subject:
        """Save a subject."""
        db_subject = subject_to_model(subject)
        with self._get_session() as session:
            merged = session.merge(db_subject)  # merge handles both insert and update
            session.commit()
            return model_to_subject(merged)

    def find_by_id(self, subject_id: str) -> Optional[Subject]:
        """Find subject by ID."""
        with self._get_session() as session:
            db_subject = session.query(SubjectModel).filter(
                SubjectModel.id == subject_id
            ).first()
            return model_to_subject(db_subject) if db_subject else None

    def find_all(self, sort_by: str = "date_added", sort_order: str = "desc") -> List[Subject]:
        """Find all subjects with optional sorting."""
        with self._get_session() as session:
            query = session.query(SubjectModel)

            # Apply sorting based on sort_by parameter
            if sort_by == "name" or sort_by == "id":
                if sort_order == "asc":
                    query = query.order_by(SubjectModel.id.asc())
                else:
                    query = query.order_by(SubjectModel.id.desc())
            elif sort_by == "date_added":
                if sort_order == "asc":
                    query = query.order_by(SubjectModel.date_added.asc())
                else:
                    query = query.order_by(SubjectModel.date_added.desc())
            elif sort_by == "sex":
                if sort_order == "asc":
                    query = query.order_by(SubjectModel.sex.asc())
                else:
                    query = query.order_by(SubjectModel.sex.desc())
            elif sort_by == "designation":
                if sort_order == "asc":
                    query = query.order_by(SubjectModel.designation.asc())
                else:
                    query = query.order_by(SubjectModel.designation.desc())
            else:
                # Default sorting by date_added desc
                query = query.order_by(SubjectModel.date_added.desc())

            db_subjects = query.all()
            return [model_to_subject(db_subject) for db_subject in db_subjects]

    def delete(self, subject_id: str) -> bool:
        """Delete subject by ID."""
        with self._get_session() as session:
            result = session.query(SubjectModel).filter(
                SubjectModel.id == subject_id
            ).delete()
            session.commit()
            return result > 0

class ExperimentRepository(BaseRepository):
    """Repository for experiment operations."""

    def save(self, experiment: Experiment) -> Experiment:
        """Save an experiment."""
        db_experiment = experiment_to_model(experiment)
        with self._get_session() as session:
            merged = session.merge(db_experiment)
            session.commit()
            return model_to_experiment(merged)

    def find_by_id(self, experiment_id: str) -> Optional[Experiment]:
        """Find experiment by ID."""
        with self._get_session() as session:
            db_experiment = session.query(ExperimentModel).filter(
                ExperimentModel.id == experiment_id
            ).first()
            return model_to_experiment(db_experiment) if db_experiment else None

    def find_by_subject(self, subject_id: str) -> List[Experiment]:
        """Find experiments by subject ID."""
        with self._get_session() as session:
            db_experiments = session.query(ExperimentModel).filter(
                ExperimentModel.subject_id == subject_id
            ).all()
            return [model_to_experiment(db_exp) for db_exp in db_experiments]

    def find_all(self, sort_by: str = "date_recorded", sort_order: str = "desc") -> List[Experiment]:
        """Find all experiments with optional sorting."""
        with self._get_session() as session:
            query = session.query(ExperimentModel)

            # Apply sorting based on sort_by parameter
            if sort_by == "date_recorded":
                if sort_order == "asc":
                    query = query.order_by(ExperimentModel.date_recorded.asc())
                else:
                    query = query.order_by(ExperimentModel.date_recorded.desc())
            elif sort_by == "experiment_type":
                if sort_order == "asc":
                    query = query.order_by(ExperimentModel.experiment_type.asc())
                else:
                    query = query.order_by(ExperimentModel.experiment_type.desc())
            elif sort_by == "processing_stage":
                if sort_order == "asc":
                    query = query.order_by(ExperimentModel.processing_stage.asc())
                else:
                    query = query.order_by(ExperimentModel.processing_stage.desc())
            elif sort_by == "date_added":
                if sort_order == "asc":
                    query = query.order_by(ExperimentModel.date_added.asc())
                else:
                    query = query.order_by(ExperimentModel.date_added.desc())
            else:
                # Default sorting by date_recorded desc
                query = query.order_by(ExperimentModel.date_recorded.desc())

            db_experiments = query.all()
            return [model_to_experiment(db_exp) for db_exp in db_experiments]

    def delete(self, experiment_id: str) -> bool:
        """Delete experiment by ID."""
        with self._get_session() as session:
            result = session.query(ExperimentModel).filter(
                ExperimentModel.id == experiment_id
            ).delete()
            session.commit()
            return result > 0


class VideoRepository(BaseRepository):
    """Repository for video file operations."""

    def save(self, video: VideoFile) -> VideoFile:
        """Save a video file record."""
        db_video = VideoModel(
            path=str(video.path),
            hash=video.hash,
            recorded_time=video.recorded_time,
            size_bytes=video.size_bytes,
            last_modified=video.last_modified,
            date_added=video.date_added
        )
        with self._get_session() as session:
            session.add(db_video)
            session.commit()
            # Convert back to domain object
            return VideoFile(
                path=Path(db_video.path),
                hash=db_video.hash,
                recorded_time=db_video.recorded_time,
                size_bytes=db_video.size_bytes,
                last_modified=db_video.last_modified,
                date_added=db_video.date_added
            )

    def find_by_hash(self, hash_value: str) -> Optional[VideoFile]:
        """Find video by hash."""
        with self._get_session() as session:
            db_video = session.query(VideoModel).filter(
                VideoModel.hash == hash_value
            ).first()
            if db_video:
                return VideoFile(
                    path=Path(db_video.path),
                    hash=db_video.hash,
                    recorded_time=db_video.recorded_time,
                    size_bytes=db_video.size_bytes,
                    last_modified=db_video.last_modified,
                    date_added=db_video.date_added
                )
        return None

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Find videos with duplicate hashes."""
        with self._get_session() as session:
            # Group by hash and find groups with multiple entries
            from sqlalchemy import func
            duplicates = session.query(
                VideoModel.hash,
                func.count(VideoModel.id).label('count')
            ).group_by(VideoModel.hash).having(func.count(VideoModel.id) > 1).all()

            result = []
            for hash_val, count in duplicates:
                videos = session.query(VideoModel).filter(
                    VideoModel.hash == hash_val
                ).all()
                result.append({
                    'hash': hash_val,
                    'count': count,
                    'videos': [{
                        'path': v.path,
                        'size': v.size_bytes,
                        'modified': v.last_modified
                    } for v in videos]
                })
            return result

class WorkerRepository(BaseRepository):
    """Repository for worker operations."""

    def save(self, worker: Worker) -> Worker:
        """Save a worker."""
        db_worker = WorkerModel(
            name=worker.name,
            ssh_alias=worker.ssh_alias,
            role=worker.role,
            provider=worker.provider.value,
            os_type=worker.os_type
        )
        with self._get_session() as session:
            merged = session.merge(db_worker)
            session.commit()
            # Convert back to domain object
            return Worker(
                name=merged.name,
                ssh_alias=merged.ssh_alias,
                role=merged.role,
                provider=worker.provider,  # Keep original enum
                os_type=merged.os_type
            )

    def find_by_name(self, name: str) -> Optional[Worker]:
        """Find worker by name."""
        with self._get_session() as session:
            db_worker = session.query(WorkerModel).filter(
                WorkerModel.name == name
            ).first()
            if db_worker:
                from .metadata import WorkerProvider
                return Worker(
                    name=db_worker.name,
                    ssh_alias=db_worker.ssh_alias,
                    role=db_worker.role,
                    provider=WorkerProvider(db_worker.provider),
                    os_type=db_worker.os_type
                )
        return None

    def find_all(self) -> List[Worker]:
        """Find all workers."""
        with self._get_session() as session:
            db_workers = session.query(WorkerModel).all()
            workers = []
            for db_worker in db_workers:
                from .metadata import WorkerProvider
                workers.append(Worker(
                    name=db_worker.name,
                    ssh_alias=db_worker.ssh_alias,
                    role=db_worker.role,
                    provider=WorkerProvider(db_worker.provider),
                    os_type=db_worker.os_type
                ))
            return workers

class ScanTargetRepository(BaseRepository):
    """Repository for scan target operations."""

    def save(self, target: ScanTarget) -> ScanTarget:
        """Save a scan target."""
        import json
        db_target = ScanTargetModel(
            name=target.name,
            kind=target.kind.value,
            roots=json.dumps([str(p) for p in target.roots]),
            ssh_alias=target.ssh_alias
        )
        with self._get_session() as session:
            merged = session.merge(db_target)
            session.commit()
            # Convert back to domain object
            return ScanTarget(
                name=merged.name,
                kind=target.kind,  # Keep original enum
                roots=[Path(p) for p in json.loads(merged.roots)],
                ssh_alias=merged.ssh_alias
            )

    def find_by_name(self, name: str) -> Optional[ScanTarget]:
        """Find scan target by name."""
        with self._get_session() as session:
            db_target = session.query(ScanTargetModel).filter(
                ScanTargetModel.name == name
            ).first()
            if db_target:
                import json
                from .metadata import ScanTargetKind
                return ScanTarget(
                    name=db_target.name,
                    kind=ScanTargetKind(db_target.kind),
                    roots=[Path(p) for p in json.loads(db_target.roots)],
                    ssh_alias=db_target.ssh_alias
                )
        return None

    def find_all(self) -> List[ScanTarget]:
        """Find all scan targets."""
        with self._get_session() as session:
            db_targets = session.query(ScanTargetModel).all()
            targets = []
            for db_target in db_targets:
                import json
                from .metadata import ScanTargetKind
                targets.append(ScanTarget(
                    name=db_target.name,
                    kind=ScanTargetKind(db_target.kind),
                    roots=[Path(p) for p in json.loads(db_target.roots)],
                    ssh_alias=db_target.ssh_alias
                ))
            return targets

class UserRepository(BaseRepository):
    """Repository for user operations."""

    def save(self, user) -> 'User':
        """Save a user."""
        from .metadata import User
        from .schema import user_to_model, model_to_user
        db_user = user_to_model(user)
        with self._get_session() as session:
            merged = session.merge(db_user)  # merge handles both insert and update
            session.commit()
            return model_to_user(merged)

    def find_by_id(self, user_id: str) -> Optional['User']:
        """Find user by ID."""
        from .schema import UserModel, model_to_user
        with self._get_session() as session:
            db_user = session.query(UserModel).filter(
                UserModel.id == user_id
            ).first()
            return model_to_user(db_user) if db_user else None

    def find_by_email(self, email: str) -> Optional['User']:
        """Find user by email."""
        from .schema import UserModel, model_to_user
        with self._get_session() as session:
            db_user = session.query(UserModel).filter(
                UserModel.email == email
            ).first()
            return model_to_user(db_user) if db_user else None

    def find_all(self) -> List['User']:
        """Find all users."""
        from .schema import UserModel, model_to_user
        with self._get_session() as session:
            db_users = session.query(UserModel).all()
            return [model_to_user(db_user) for db_user in db_users]

class LabRepository(BaseRepository):
    """Repository for lab operations."""

    def save(self, lab) -> 'Lab':
        """Save a lab."""
        from .metadata import Lab
        from .schema import lab_to_model, model_to_lab
        db_lab = lab_to_model(lab)
        with self._get_session() as session:
            merged = session.merge(db_lab)  # merge handles both insert and update
            session.commit()
            return model_to_lab(merged)

    def find_by_id(self, lab_id: str) -> Optional['Lab']:
        """Find lab by ID."""
        from .schema import LabModel, model_to_lab
        with self._get_session() as session:
            db_lab = session.query(LabModel).filter(
                LabModel.id == lab_id
            ).first()
            return model_to_lab(db_lab) if db_lab else None

    def find_by_creator(self, creator_id: str) -> List['Lab']:
        """Find labs by creator ID."""
        from .schema import LabModel, model_to_lab
        with self._get_session() as session:
            db_labs = session.query(LabModel).filter(
                LabModel.creator_id == creator_id
            ).all()
            return [model_to_lab(db_lab) for db_lab in db_labs]

    def find_all(self) -> List['Lab']:
        """Find all labs."""
        from .schema import LabModel, model_to_lab
        with self._get_session() as session:
            db_labs = session.query(LabModel).all()
            return [model_to_lab(db_lab) for db_lab in db_labs]

    def add_project(self, lab_id: str, project_name: str, project_path: Path, created_date) -> None:
        """Add a project to a lab."""
        from .schema import LabProjectModel
        from datetime import datetime
        db_project = LabProjectModel(
            lab_id=lab_id,
            name=project_name,
            path=str(project_path),
            created_date=created_date or datetime.now()
        )
        with self._get_session() as session:
            session.add(db_project)
            session.commit()

    def get_projects(self, lab_id: str) -> List[Dict[str, Any]]:
        """Get all projects for a lab."""
        from .schema import LabProjectModel
        with self._get_session() as session:
            db_projects = session.query(LabProjectModel).filter(
                LabProjectModel.lab_id == lab_id
            ).all()
            return [{
                'name': p.name,
                'path': p.path,
                'created_date': p.created_date
            } for p in db_projects]

# ===========================================
# REPOSITORY FACTORY
# ===========================================

class RepositoryFactory:
    """Factory for creating repositories."""

    def __init__(self, db: Database):
        self.db = db
        self._users: Optional[UserRepository] = None
        self._labs: Optional[LabRepository] = None
        self._colonies: Optional[ColonyRepository] = None
        self._subjects: Optional[SubjectRepository] = None
        self._experiments: Optional[ExperimentRepository] = None
        self._videos: Optional[VideoRepository] = None
        self._workers: Optional[WorkerRepository] = None
        self._scan_targets: Optional[ScanTargetRepository] = None

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            self._users = UserRepository(self.db)
        return self._users

    @property
    def labs(self) -> LabRepository:
        if self._labs is None:
            self._labs = LabRepository(self.db)
        return self._labs

    @property
    def colonies(self) -> ColonyRepository:
        if self._colonies is None:
            self._colonies = ColonyRepository(self.db)
        return self._colonies

    @property
    def subjects(self) -> SubjectRepository:
        if self._subjects is None:
            self._subjects = SubjectRepository(self.db)
        return self._subjects

    @property
    def experiments(self) -> ExperimentRepository:
        if self._experiments is None:
            self._experiments = ExperimentRepository(self.db)
        return self._experiments

    @property
    def videos(self) -> VideoRepository:
        if self._videos is None:
            self._videos = VideoRepository(self.db)
        return self._videos

    @property
    def workers(self) -> WorkerRepository:
        if self._workers is None:
            self._workers = WorkerRepository(self.db)
        return self._workers

    @property
    def scan_targets(self) -> ScanTargetRepository:
        if self._scan_targets is None:
            self._scan_targets = ScanTargetRepository(self.db)
        return self._scan_targets
