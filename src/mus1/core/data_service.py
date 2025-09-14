"""
Clean data service demonstrating Domain -> DTO -> Database -> Domain pattern.

This shows how to use the simplified metadata models with SQLite backend.
"""

import json
from typing import List, Optional
from .metadata import Subject, Experiment, SubjectDTO, ExperimentDTO, Sex, ProcessingStage
from .schema import Database, SubjectModel, ExperimentModel, subject_to_model, model_to_subject, experiment_to_model, model_to_experiment

class SubjectService:
    """Service for managing subjects with clean data flow."""

    def __init__(self, db: Database):
        self.db = db

    def create_subject(self, subject_dto: SubjectDTO) -> Subject:
        """Create a subject: DTO -> Domain -> Database -> Domain."""
        # DTO validation happens automatically via Pydantic
        subject_dto_dict = subject_dto.dict()

        # Create domain model
        domain_subject = Subject(**subject_dto_dict)

        # Convert to database model and save
        db_subject = subject_to_model(domain_subject)
        with self.db.get_session() as session:
            session.add(db_subject)
            session.commit()
            session.refresh(db_subject)

        # Return domain model
        return model_to_subject(db_subject)

    def get_subject(self, subject_id: str) -> Optional[Subject]:
        """Get a subject: Database -> Domain."""
        with self.db.get_session() as session:
            db_subject = session.query(SubjectModel).filter(SubjectModel.id == subject_id).first()
            if db_subject:
                return model_to_subject(db_subject)
        return None

    def list_subjects(self) -> List[Subject]:
        """List all subjects: Database -> Domain."""
        with self.db.get_session() as session:
            db_subjects = session.query(SubjectModel).all()
            return [model_to_subject(db_subject) for db_subject in db_subjects]

class ExperimentService:
    """Service for managing experiments with clean data flow."""

    def __init__(self, db: Database):
        self.db = db

    def create_experiment(self, experiment_dto: ExperimentDTO) -> Experiment:
        """Create an experiment: DTO -> Domain -> Database -> Domain."""
        # DTO validation
        experiment_dto_dict = experiment_dto.dict()

        # Create domain model
        domain_experiment = Experiment(**experiment_dto_dict)

        # Convert to database model and save
        db_experiment = experiment_to_model(domain_experiment)
        with self.db.get_session() as session:
            session.add(db_experiment)
            session.commit()
            session.refresh(db_experiment)

        # Return domain model
        return model_to_experiment(db_experiment)

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get an experiment: Database -> Domain."""
        with self.db.get_session() as session:
            db_experiment = session.query(ExperimentModel).filter(ExperimentModel.id == experiment_id).first()
            if db_experiment:
                return model_to_experiment(db_experiment)
        return None

    def list_experiments(self) -> List[Experiment]:
        """List all experiments: Database -> Domain."""
        with self.db.get_session() as session:
            db_experiments = session.query(ExperimentModel).all()
            return [model_to_experiment(db_experiment) for db_experiment in db_experiments]

# ===========================================
# EXAMPLE USAGE
# ===========================================

def example_usage():
    """Example of clean data flow."""

    # Initialize database
    db = Database(":memory:")
    db.create_tables()

    # Create services
    subject_service = SubjectService(db)
    experiment_service = ExperimentService(db)

    # Create subject via DTO
    subject_dto = SubjectDTO(
        id="SUB001",
        sex=Sex.MALE,
        genotype="ATP7B:WT",
        notes="Test subject"
    )

    # Clean flow: DTO -> Domain -> Database -> Domain
    subject = subject_service.create_subject(subject_dto)
    print(f"Created subject: {subject.id}, age: {subject.age_days} days")

    # Create experiment
    experiment_dto = ExperimentDTO(
        id="EXP001",
        subject_id=subject.id,
        experiment_type="OpenField",
        date_recorded="2024-01-01T10:00:00"
    )

    experiment = experiment_service.create_experiment(experiment_dto)
    print(f"Created experiment: {experiment.id}, ready for analysis: {experiment.is_ready_for_analysis}")

    # Retrieve data
    retrieved_subject = subject_service.get_subject("SUB001")
    print(f"Retrieved subject genotype: {retrieved_subject.genotype}")

if __name__ == "__main__":
    example_usage()
