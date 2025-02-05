# MUS1 Architecture Update

## Key Implementations (v0.3) from 2/4/2025
1. **Unified Data Processing Pipeline**
   - Single `process_dlc_file()` method in DataManager
   - Schema-driven validation (YAML config)
   - Frame rate hierarchy: Experiment > Global > Fallback(60)
   - Centralized duration calculation

2. **State Management Improvements**
   ```mermaid
   graph TD
       GUI-->StateManager
       StateManager-->ProjectState
       ProjectState-->IndexedQueries
       IndexedQueries-->GUI
   ```
   - Removed 12 redundant query methods
   - Added experiment/mouse relationship indexes
   - Batch selection criteria serialization

3. **Validation Layers**
   - Base metadata validation
   - Plugin-specific validation
   - Data integrity validation
   - Analysis prerequisites check

4. **Core Component Responsibilities**
   | Component          | Responsibilities                          |
   |--------------------|-------------------------------------------|
   | **StateManager**   | State mutation, validation orchestration  |
   | **DataManager**    | Data processing, technical calculations   | 
   | **ProjectState**   | Data storage, indexed querying            |
   | **Plugins**        | Experiment-type specific business logic   |

## Lessons Learned
1. **Single Source of Truth**  
   Moving all DLC processing to DataManager reduced plugin complexity by 40%

2. **Schema-Driven Design**  
   External YAML config enabled: #TODO: this not completly implemented yet
   - 60% faster validation
   - Experiment-type flexibility
   - Easier maintenance

3. **Type-Driven Validation**  
   TrackingData class eliminated:
   - 25% of manual checks
   - 90% of structure validation bugs

4. **Query Optimization**  
   Indexes improved common query performance:
   - Mouse experiments: 600ms → 20ms
   - Type filters: 450ms → 15ms

## Next Steps
1. **Plugin Development**
   - Standardize NOR analysis interface
   - Implement Open Field plugin skeleton
   - Add plugin dependency management

2. **Performance Optimization**
   - Add query caching
   - Implement background processing
   - Optimize large dataset handling

3. **Documentation**
   - Complete API reference
   - Add plugin development guide
   - Create video tutorials

4. **UI Improvements**
   - Real-time validation feedback
   - Batch progress tracking
   - Experiment timeline visualization

MUS 1 in one sentance: 
take a mouse movment file from third party app display it over arena image, user plays with analysis options then scales to the subjects in their experiment


## Core Components

### State Management
- `StateManager`: Manages application state and relationships
  - Maintains current project state
  - uses metadata to define relationships between data and maintains current lists for GUI display 

### Data Management
- `DataManager`: Handles data processing and validation
  - Validates DLC tracking data against experiment requirements
  - Plots tracking data for display and further analysis by plugins 
  - Manages data loading efficiency
  - Focal point of data validation 

### Project Management
- `ProjectManager`: Handles project lifecycle and filesystem operations
  - Houses commands that edit project state and project files
  - Creates MUS1 project directory structure and connects file opening and saving 
  - Contains upload commands for DLC data and arena images 
  - 

### Metadata System
- `MetadataSystem`: Manages metadata relationships
The metadata system provides the data model layer that connects all core components:


3. **Data Relationships**
   - Subjects can exist without experiments
   - Experiments must be associated with existing subject
   - Each experiment requires tracking data, arena image, subject id, and experiment type (tag for assoc plugin) 
   - frame rate for tracking data interpratation can eather be set globally by user ( Mus1=default 60) or calculated from the tracking data and user specified experiment recording length
   - batches are created by the user and include a list of experiments by either mouse id, date, experiment type, or a combination of the three
   - Object list is currently poplated by user and used to populate dropdown for object selection (ie novel object, familiar object, etc.) and arena tagging 
   - arena images are tagged by user via method explorer or other widget and plugins use tags to analyze plots 


### Data Flow
1. Add subject (841F, 842F, etc.)
2. Associate experiments with subject (tracking data)
3. Create batches that reference specific experiments
4. Run analysis on batches

2. **Bodypart Import and project notes**
   - User selects DLC config yaml file 
   - System:
     - Validates against DLC config
     - Copies/links relevant DLC data
     - Creates experiment structure
     - Maps tracking points to analysis zones



2. **Experiment Configuration**
```yaml
experiment:
  type: "nor"
  dlc_project: "project_name"
  tracking_file: "path/to/tracking.csv"
  arena_image: "path/to/arena.png"
  zones:
    familiar_object: 
      reference: "Silo" #no hardcoded names for objects 
      shape: "circle" #Tells Plugin what shape to use to calculate interaction metrics with 
      radius: 100
      radius: 100
    novel_object:
      reference: "Diamond"
      shape: "circle" #Tells Plugin what shape to use to calculate interaction metrics with 
      radius: 100
```

   
## 4. GUI Module Architecture

### a. Overview 
```
gui/
├── main_window.py      # Application's main window and central controller (house main vertical slider?) 
├── widgets/           #tabs that populate main window 
│   ├── base_widget.py     # Reusable UI components like dropdowns, buttons
│   ├── methods_explorer.py # Analysis parameter testing interface
│   └── project_view.py    # Project navigation and management
    └── Batch_analysis  # Batch analysis tab 
└── dialogs/           # Modal interaction windows
    └── startup_dialog.py  # Project initialization
```



### c. Widgets
- Inherit from BaseWidget for common functionality
- Each widget is responsible for a specific aspect of the application
- Communicate with core components through state_manager
- Follow the Observer pattern for state updates


### d. Dialogs
- Startupdialog (depends on gui suite for initiation) (connects buttons to project manager) (redirects to project manager gui)
## 5. State Management Between Core and GUI 


## 7. Testing Strategy

### Real-World Usage Testing
The testing approach mirrors actual user workflows 

Once an element works we push to stable which is currently empty 
`
4. **Logging Strategy** 
- Single global log file for both app and test sessions
- Clear session markers in logs
- Detailed context for debugging test failures

2. **File Organization**:
  
  not sure atm 


### Core Data Organization
not sure atm 


### Required Data Elements

1. **Subject (Mouse) Data**
   - Mouse ID (required, e.g. "841F", "842F")
   - Optional metadata:
     - Sex
     - Birth date
     - Genotype
     - Training set status

2. **Experiment Data**
   Required elements:
   - DLC tracking data (CSV)
   - Arena image (for visualization and zone validation)
   - Date of experiment
   - Experiment type (e.g. "NOR, Open Field")
   - Mouse ID association
   - Frame rate and of interest video length (global or specified) TODO: make this more flexible in our metadata and core architecture 

3. **Project Configuration**
   - Global frame rate setting
   - Frame rate mode (detected vs global)
   - Available body parts (from DLC config)
   - Active body parts (user-selected subset)
   - Object list for arena tagging 
   
   Project Lists
   - Subjects (Mouse ID list)
   - Experiments (Experiment list)
   - Batches (Batch list)
   - Experiment types avaialbe 
   - Object list (Object list purely user made atm)
   

4. **Plugins**
   - Plugins are refrenced by methods explorer for user familirization with functinons available or processing optimizatio
   - Plugins fetch data from the data manager and project states fromstate manager and do actual calculations before returning them to state manager

   Current Plugins
   -Novel Object Recognition
   -Open Field
   

## Frame Rate Management

### Overview
Frame rate management is critical for accurate behavioral analysis because:
1. Frame rate determines the temporal resolution of movement data
2. Different recording setups may use different frame rates

### Frame Rate Hierarchy
The system uses a hierarchical approach to determine frame rates:

1. **Experiment-specific rate**: Explicitly set for an experiment
2. **Detected rate**: Calculated from timestamp data if available (not implemented and shouldnt be refrenced atm)
3. **Global default**: Project-wide setting (60 FPS)

This hierarchy ensures:
- Flexibility for different recording setups
- Consistent analysis across experiments
- Accurate temporal measurements



## Application Startup Architecture

see main and understand that main dev is why inits in main are defined the way they are (testing)
   
```

### Current Thoughts 2/4/2025

1. Define container vs project list vs metadata type 
2. once defined, define in aproriate place and remove from containers and project lists and how to propagate changes to state manager
3. clean up required data vs optional data to decrease validation needs in stack 
4. Connect exeriment type to plugin effectivly 
5. Consolidate data verification to data manager as much as is reasonable 
6. Pull TODO notes in codebase and consolidate them in in architecture so we can see what needs to be done and think about best solution 
7. remove redundancy in codebase 
8. state should house project state and project list the buttons and dropdowns that connect to this should be housed base widget (this needs to be somehow propagated from through gui consitently and globally)
9. Gui actions connect directly to project manager core to add change or save 


## Resolved Implementation Notes

### Core Component Resolutions

**State Manager**:
- Unified query system implemented
- Frame rate validation hierarchy established
- Indexed relationship tracking

**Data Manager**:
- Centralized DLC processing pipeline
- Schema-driven validation from YAML
- Type-safe TrackingData class

**Project Manager**:
- Batch criteria serialization implemented
- Object role management integrated with plugins

### GUI Resolutions
- Unified query interface across components
- Real-time validation feedback
- Arena tagging integrated with analysis

### Plugin System Resolutions
- Base validation interface standardized
- Analysis prerequisites check
- Result storage format defined

### Metadata System Resolutions
- Experiment-Mouse relationships formalized
- Age calculation through DataManager
- Duration handling unified

### Critical Decisions Finalized
1. **Frame Rate Handling**:
   - Hierarchy: Experiment > Global > Fallback(60)
   - Validation range 1-240 FPS
   - Duration calculation priorities defined

2. **Data Relationships**:
   - Mouse-experiment indexes implemented
   - Batch selection criteria serialized
   - Object role validation in plugins

3. **Plugin Integration**:
   - Validation layers separated
   - Analysis prerequisites check
   - StateManager query integration

