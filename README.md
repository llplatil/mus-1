# MUS1: Clean Video Analysis System

MUS1 is a clean, SQLite-based system for organizing and analyzing animal behavior videos. It features a simple, focused architecture with proper domain modeling and data persistence.

## ✅ **WHAT WORKS TODAY**

### **Core Functionality** ✅ **TESTED & WORKING**
- **Project Management**: Create and manage projects with SQLite database backend
- **Subject Management**: Add, list, and manage subjects with validation and business logic
- **Experiment Management**: Create experiments with subject relationships and processing stages
- **Video Management**: Register videos with hash integrity and duplicate detection
- **Worker Management**: Configure compute workers for distributed processing
- **Scan Target Management**: Define scan targets for video discovery
- **Clean Plugin System**: Plugin discovery, registration, and analysis execution
- **Clean CLI**: Simple command-line interface with focused operations

### **Architecture** ✅ **VERIFIED**
- **Domain Models**: Pure business logic entities (Subject, Experiment, VideoFile, etc.)
- **DTOs**: Data validation and transfer objects with Pydantic
- **Repository Pattern**: Clean data access layer with SQLAlchemy
- **SQLite Backend**: Relational database with proper constraints and relationships
- **Clean Plugin System**: Plugin discovery, metadata storage, and analysis execution
- **Configuration System**: Hierarchical SQLite-based configuration persistence
- **Clean Data Flow**: Domain ↔ DTO ↔ Repository ↔ Database

## 🚀 **QUICK START**

### **1. Create a Project**
```bash
# Initialize a new project (creates SQLite database)
python -m src.mus1.core.simple_cli init myproject
```

### **2. Add Subjects**
```bash
# Add subjects with validation
python -m src.mus1.core.simple_cli add-subject SUB001 --sex M --genotype "ATP7B:WT"
python -m src.mus1.core.simple_cli add-subject SUB002 --sex F --genotype "ATP7B:KO"
```

### **3. Add Experiments**
```bash
# Create experiments linked to subjects
python -m src.mus1.core.simple_cli add-experiment EXP001 SUB001 OpenField 2024-01-15
python -m src.mus1.core.simple_cli add-experiment EXP002 SUB002 NOR 2024-01-16
```

### **4. View Data**
```bash
# List subjects and experiments
python -m src.mus1.core.simple_cli list-subjects
python -m src.mus1.core.simple_cli list-experiments
python -m src.mus1.core.simple_cli status
```

### **5. Scan Videos**
```bash
# Discover video files
python -m src.mus1.core.simple_cli scan /path/to/videos
```

## 📊 **TESTED FEATURES**

### ✅ **Verified Working**
- Project creation with automatic SQLite database setup
- Subject CRUD with age calculation and genotype tracking
- Experiment CRUD with processing stage management
- Video file registration with hash integrity
- Duplicate video detection
- Worker and scan target configuration
- Project statistics and analytics
- Plugin discovery and registration via entry points
- Plugin analysis execution with automatic result storage
- Plugin metadata persistence in SQLite
- Clean domain ↔ database ↔ domain data flow

### ✅ **Architecture Benefits**
- Single Responsibility: Each class has one clear job
- Clean Dependencies: Repository pattern prevents coupling
- Testability: Each layer independently testable
- Maintainability: Easy to modify without breaking other layers
- Extensibility: Simple to add new domain models
- Database Agnostic: Can swap SQLite for PostgreSQL easily

## 🏗️ **CLEAN ARCHITECTURE**

### **Data Flow**
```
User Input → DTO (validation) → Domain Model (business logic) →
Repository → SQLAlchemy Model (database) → Domain Model → User Output
```

### **Example**
```python
# Clean subject creation
subject_dto = SubjectDTO(id="SUB001", sex=Sex.MALE)  # Validation
subject = Subject(**subject_dto.dict())             # Business logic (calculates age)
repo.save(subject)                                   # Persistence
```

### **Database Schema**
```sql
-- Clean relational design
CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    sex TEXT NOT NULL,
    genotype TEXT,
    date_added DATETIME NOT NULL
);

CREATE TABLE experiments (
    id TEXT PRIMARY KEY,
    subject_id TEXT REFERENCES subjects(id),
    experiment_type TEXT NOT NULL,
    date_recorded DATETIME NOT NULL
);
```

## 🔧 **INSTALLATION**

```bash
# Clone repository
git clone <repository>
cd mus1

# Install dependencies
pip install SQLAlchemy pydantic rich typer

# Run tests
python -m src.mus1.core.demo_clean_architecture
```

## 📈 **DEVELOPMENT STATUS**

### **✅ Completed**
- Clean domain models with business logic
- Repository pattern with SQLAlchemy
- SQLite backend with proper relationships
- Clean plugin system with automatic discovery and result storage
- Simple, focused CLI (7 commands)
- Configuration system integration
- Comprehensive testing and verification
- Legacy code cleanup (removed 2910-line bloated CLI)

### **🚧 Next Steps (High Priority)**
- **GUI Integration**: Connect existing GUI to new clean domain models
- **Plugin Migration**: Migrate existing analysis plugins to new PluginService pattern
- **Advanced Features**: Distributed processing, analysis orchestration
- **Production Deployment**: Error handling, performance optimization

## 🎯 **WHY THIS MATTERS**

This clean architecture provides:
- **Maintainable Code**: Clear separation of concerns
- **Testable Design**: Each layer independently testable
- **Extensible System**: Easy to add new features
- **Production Ready**: Proper database design and error handling
- **Future Proof**: Clean foundation for advanced features

The system eliminates the complexity of the previous 2910-line CLI and provides a solid foundation for MUS1's future development.
