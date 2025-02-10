# MUS1 Development Roadmap

## Phase 1: Core Foundation (MVP)
### 1.1 Project Structure and Data Management
- [x] Set up basic project structure
- [x] Implement core data structures (MouseMetadata, ExperimentMetadata, etc.)
- [x] Create basic project file handling
- [x] Implement DLC config file parsing
- [x] Design standardized experiment directory structure

### 1.2 State Management
- [x] Implement StateManager with proper event system
- [x] Create DataManager for file operations
- [x] Set up ProjectManager for project lifecycle
- [x] Implement error handling system
- [x] Add timeline-aware experiment organization
- [x] Implement experiment phase validation
- [ ] Add state dialog for project creation/loading

### 1.3 Plugin Architecture
- [ ] Design plugin interface for analysis methods
- [ ] Create base plugin class
- [ ] Implement plugin loading system
- [ ] Create example NOR (Novel Object Recognition) plugin

### 1.4 Testing Infrastructure
- [x] Setup test data with real DLC examples
- [x] Create test project lifecycle management
- [x] Implement global logging for app/tests
- [ ] Add end-to-end workflow tests
- [ ] Create test utilities for common operations
- [ ] Add cleanup utilities for test projects

## Phase 2: Basic Analysis Features
### 2.1 Data Import
- [x] Import DLC tracking data (CSV)
- [x] Import arena images
- [x] Basic data validation
- [x] Mouse metadata management
- [x] Memory-efficient data loading
- [ ] Batch import capabilities

### 2.2 Analysis Tools
- [ ] Basic trajectory visualization
- [ ] Zone definition tools
- [ ] Time in zone analysis
- [ ] Distance traveled calculation
- [ ] Movement speed analysis

### 2.3 Methods Explorer
- [ ] Parameter testing interface
- [ ] Real-time visualization
- [ ] Parameter preset system
- [ ] Result comparison tools

## Phase 3: Advanced Features
### 3.1 Experiment Management
- [ ] Multi-session experiment support
- [ ] Experiment type templates
- [ ] Batch processing capabilities
- [ ] Data export tools

### 3.2 Analysis Plugins
- [ ] EPM (Elevated Plus Maze) analysis
- [ ] Open Field analysis
- [ ] Social Interaction analysis
- [ ] Custom plugin support

### 3.3 Visualization and Export
- [ ] Advanced plotting options
- [ ] Statistical analysis tools
- [ ] Report generation
- [ ] Data export formats (CSV, Excel, etc.)

## Phase 4: Quality of Life Features
### 4.1 User Interface
- [ ] Project management interface
- [ ] Analysis workflow wizards
- [ ] Batch processing interface
- [ ] Settings management

### 4.2 Data Management
- [ ] Project backup/restore
- [ ] Data validation tools
- [ ] Metadata management
- [ ] File organization tools

### 4.3 Documentation
- [ ] User manual
- [ ] API documentation
- [ ] Analysis method documentation
- [ ] Example workflows

## Future Considerations
- Video handling and playback
- Machine learning integration
- Multi-animal tracking support
- Remote data storage/sharing
- Integration with other analysis tools

## Notes
- Priority is given to core functionality and NOR analysis
- Each phase builds on previous phases
- Focus on stability and usability before adding features
- Regular testing and documentation updates throughout
- Timeline-aware data organization is critical for analysis
- Memory efficiency is prioritized for large datasets


# Key Design Principles
> These principles guide all [development phases](ROADMAP.md)

1. **Separation of Concerns**
   - Core logic separate from UI
   - Modular plugin system
   - Clear and consitent data flow paths

2. **Data Integrity**
   - Use metadata and required data to minimize errrors and validation needs 
   - Only meaningful data validation


3. **Extensibility**
   - Plugin-based analysis
   - Accelerate behavior analysis (Automate arena detection and object detection + generative labeling)
   -intgrate with more apps and tools (Keypoint Mo Seq support)



## Future Considerations
> See [Phase 4 and beyond](ROADMAP.md#phase-4-quality-of-life-features)

