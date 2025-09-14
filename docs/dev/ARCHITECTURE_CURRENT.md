# MUS1 Clean Architecture — Current State (authoritative)

This document describes the **new clean MUS1 architecture** that works today, based on our successful refactoring.

## ✅ WHAT WORKS TODAY

### Clean Architecture Components

#### 1. Domain Models (`src/mus1/core/metadata.py`) ✅ WORKING
- **Subject**: Pure business entity with age calculation
- **Experiment**: Experiment entity with analysis readiness
- **VideoFile**: Video file tracking with hash integrity
- **Worker**: Compute worker configuration
- **ScanTarget**: Scan target configuration
- **Enums**: Clean Sex, ProcessingStage, WorkerProvider, ScanTargetKind

#### 2. Data Transfer Objects (DTOs) ✅ WORKING
- **SubjectDTO**: Input validation for subjects
- **ExperimentDTO**: Input validation for experiments
- **VideoFileDTO**: Input validation for videos
- **WorkerDTO/ScanTargetDTO**: Input validation for infrastructure

#### 3. SQLite Database Layer (`src/mus1/core/schema.py`) ✅ WORKING
- **SubjectModel**: SQLAlchemy model with relationships
- **ExperimentModel**: SQLAlchemy model with foreign keys
- **VideoModel**: SQLAlchemy model with integrity checks
- **WorkerModel/ScanTargetModel**: Infrastructure persistence
- **Database class**: Connection management and table creation

#### 4. Repository Layer (`src/mus1/core/repository.py`) ✅ WORKING
- **SubjectRepository**: CRUD operations with clean domain conversion
- **ExperimentRepository**: CRUD with relationship handling
- **VideoRepository**: File integrity and duplicate detection
- **RepositoryFactory**: Clean dependency injection

#### 5. Project Manager (`src/mus1/core/project_manager_clean.py`) ✅ WORKING
- **ProjectManagerClean**: Focused project operations
- **Subject management**: Add, retrieve, list, remove
- **Experiment management**: Add, retrieve, list, remove
- **Video management**: Add with duplicate detection
- **Worker/ScanTarget management**: Infrastructure configuration
- **Statistics**: Project analytics and reporting

#### 6. Simple CLI (`src/mus1/core/simple_cli.py`) ✅ WORKING
- **init**: Create new projects with SQLite database
- **add-subject**: Add subjects with validation
- **add-experiment**: Add experiments with validation
- **list-subjects/experiments**: Clean data display
- **scan**: Basic video file discovery
- **status**: Project status and statistics

#### 7. Configuration System (`src/mus1/core/config_manager.py`) ✅ WORKING
- **SQLite-based**: Hierarchical configuration persistence
- **Atomic operations**: Proper transaction handling
- **Migration support**: From old YAML/JSON configs

#### 8. Clean Plugin System (`src/mus1/core/plugin_manager_clean.py`) ✅ WORKING
- **PluginManagerClean**: Clean plugin manager with repository integration
- **PluginService**: Service layer providing data access for plugins
- **Plugin Metadata Storage**: SQLite-based plugin metadata persistence
- **Analysis Result Storage**: Automatic storage of plugin analysis results
- **Entry-point Discovery**: Automatic plugin discovery via Python entry points
  
## 🎯 HOW IT WORKS

### Clean Data Flow
```
User Input → DTO (validation) → Domain Model (business logic) →
Repository → SQLAlchemy Model (database) → Domain Model → DTO → User Output
```

### Example: Adding a Subject
```python
# 1. User provides data
subject_dto = SubjectDTO(id="SUB001", sex=Sex.MALE, genotype="ATP7B:WT")

# 2. DTO validates input automatically
# 3. Convert to domain model
subject = Subject(**subject_dto.dict())

# 4. Repository saves to database
repo = SubjectRepository(db)
saved = repo.save(subject)  # Returns domain model

# 5. Domain model has business logic
age = saved.age_days  # Automatic calculation
```

### Database Architecture
```sql
-- Clean relational schema
CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    sex TEXT NOT NULL,
    birth_date DATETIME,
    genotype TEXT,
    date_added DATETIME NOT NULL
);

CREATE TABLE experiments (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    experiment_type TEXT NOT NULL,
    date_recorded DATETIME NOT NULL,
    processing_stage TEXT NOT NULL,
    date_added DATETIME NOT NULL
);
```

## 🚫 WHAT DOESN'T WORK (YET)

### Legacy Components (Removed) ✅
- ✅ **Old CLI** (`cli_ty.py`): 2910-line bloated interface ✅ REMOVED
- ✅ **Old Project Manager**: Complex state management ✅ REMOVED
- ✅ **Old Metadata Models**: Mixed concerns ✅ REMOVED
- ✅ **Complex DataManager**: Over-engineered IO ✅ REMOVED

### Missing Features ❌
- **GUI Integration**: Not connected to clean architecture
- **Advanced Scanning**: Complex remote/distributed scanning
- **Distributed Processing**: Multi-machine job execution

## 📊 TESTED FUNCTIONALITY ✅

### Core Operations Working
- Project creation with SQLite database
- Subject CRUD (Create, Read, Update, Delete)
- Experiment CRUD with subject relationships
- Video file registration with hash integrity
- Worker and scan target management
- Project statistics and analytics
- Duplicate video detection
- Clean domain ↔ database ↔ domain conversion
- Plugin discovery and registration
- Plugin analysis execution with result storage
- Plugin metadata persistence

### Architecture Benefits Verified
- **Single Responsibility**: Each class has one clear job
- **Clean Dependencies**: Repository pattern prevents coupling
- **Testability**: Each layer independently testable
- **Maintainability**: Easy to modify without breaking other layers
- **Extensibility**: Simple to add new domain models
- **Database Agnostic**: Can swap SQLite for PostgreSQL easily

## 🔧 INTEGRATION STATUS

### Plugin System ✅ FULLY INTEGRATED
- PluginManagerClean works perfectly with new architecture
- PluginService provides clean data access for plugins
- Plugin metadata and analysis results stored in SQLite
- Automatic plugin discovery via entry points
- Clean integration with repository pattern

### Configuration System ✅ FULLY INTEGRATED
- ConfigManager works perfectly with new architecture
- Hierarchical settings (Runtime > Project > Lab > User > Install)
- SQLite persistence with atomic operations

### GUI Status ❌ NOT INTEGRATED
- Old GUI still uses broken legacy models
- Needs complete rewrite to use new clean architecture

