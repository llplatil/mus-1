# MUS1 Refactoring / Rewrite Notes

## Objectives
1. Employ modern Python libraries (Pydantic for metadata, built-in logging, PySide6/PyQt for GUI).  
2. Modernize the GUI approach:  
   - Use a single MainWindow with multiple functional tabs (Project, Subjects, Experiments, Markup, etc.).  
   - Integrate splash screen + project selection dialog seamlessly.  
3. Maintain consistency in the data model via **ProjectState** (with Pydantic) and a coherent folder structure (`mus1/core`, `mus1/gui`, `mus1/plugins`, `mus1/docs`).  
4. Support advanced features incrementally:  
   - Image/video integration and extraction.  
   - Interactive “markup” of images (draw objects / arena zones).  
   - **Flexible plugin architecture** for experiment types (NOR, OpenField, BasicCSVPlot, etc.).  

## Current Repo Restructure
1. A single "mus1/" folder, with subfolders:
   - `core/`  
   - `gui/`  
   - `plugins/`  
   - `docs/`  
   In the base of the mus1 folder:
   - `projects/` (houses mus1 projects)  
   - `mus1.log` (log file)  
   - `gitignore` (configured to ignore log file and projects folder)  
   - `README.md`  
   - `requirements.txt`  
   - `project.toml`  
   - `pytest.ini`  
2. Logging with a unified strategy in `main.py` (using Python's built-in logging or loguru):
   - Logs appended to `mus1.log` by default.
   - Each module can use `logging.getLogger(__name__)`.
3. Metadata:
   - Uses Pydantic-based classes (e.g., `MouseMetadata`, `ExperimentMetadata`, etc.).  
   - Plugin validation is handled within each plugin (e.g., `BasicCSVPlotPlugin`, `NORPlugin`, `OFPlugin`).
4. Plugin Approach:
   - Each experiment type is a plugin with logic for validation and optional analysis.
   - A `PluginManager` handles registration and lookup by experiment type.

## Metadata & Experiment Minimalism

- **Required**: `Experiment ID`, `Subject (Mouse) ID`, `Date`, `Type` (one of the registered plugins).  
- **Optional**: Additional fields that plugins can validate (stored in `experiment.plugin_params`).  
- Base enumerations (`ExperimentType`, `SessionStage`, etc.) may be minimal, with specific checks enforced by plugins.

## Step 0: Metadata Cleanup
- We have largely confirmed that plugin-specific fields (like CSV paths) are no longer embedded in the base models.  
- Enumerations appear aligned with current plugin usage.  
- Contradicting logic has been mostly removed in favor of plugin-based validations.  

**→ Step 0 is effectively complete.**

## Step 1: “Add Experiment” with Plugin-Specified Fields
- **BasicCSVPlotPlugin** is implemented with:
  - A `required_fields()` method returning `["csv_path"]`.  
  - Validation checks (e.g., CSV file path exists, overlapping body parts).  
- `ProjectManager.add_experiment(...)`:
  - Accepts minimal experiment data + `plugin_params`.  
  - Calls `plugin_manager.validate_experiment(...)`.  
  - If valid, the experiment is added to `project_state.experiments`.  
- **GUI**: `ExperimentView` handles:
  - Collecting user input for common fields + plugin fields (CSV path, etc.).  
  - Displaying validation errors if any occur.

**→ Step 1 is substantially complete**, though you may further refine the GUI (e.g., dynamic plugin forms).

Things I would like to do better:
UI/Logic Separation
keeping core logic in managers (ProjectManager, StateManager) rather than embedding it in the GUI classes. You could expand on this separation by letting the UI simply request actions from ProjectManager, which in turn calls StateManager. For instance, instead of directly manipulating project_state in your UI, consider always using manager methods. This enforces a clearer boundary (UI <-> Manager <-> State).
Plugin Field Handling in the UI
Currently, you collect plugin-specific fields (like csv_path or arena_path) in fixed form inputs. For better flexibility, the GUI could dynamically generate fields based on each plugin's required_fields() and maybe optional fields. This approach would let you handle new plugins (with entirely different fields) without adding more widgets or restructuring the layout every time.

## Where We Stand with Sorting
We introduced a **global sort approach** (via `sort_manager.py`) and began moving all list-sorting in the application to a single, unified method. Each data model that needs "Date Added" or "Name/ID" based sorting should have a consistent field (e.g., `date_added` or `name`) so that sorting is straightforward and uniform.

## Steps to Finalize the Global Sorting Implementation

**1) Add or Confirm "date_added" Fields Where Needed**  
   - Subjects (`MouseMetadata`) already have `date_added`.  
   - Experiments (`ExperimentMetadata`) have `date_added`.  
   - Plugins use `PluginMetadata.date_created`, which can be treated similarly.  
   - Body Parts, Objects, or other items that should support "Date Added" sorting may need a `date_added`.  
   - If any model does not require date-based sorting, fall back to a name- or ID-based approach.

**2) Centralize All Sorting in `sort_manager.py`**  
   - Remove or replace all `.sort(...)` calls across the code with `sort_items(...)` from `sort_manager.py`.  
   - Always retrieve the global sort mode from `project_state.settings["global_sort_mode"]` or a default.  
   - Provide a default or custom `key_func` in `sort_manager.py` if you must handle special fields (e.g., "birthday" for mouse).

**3) Update the GUI to Reflect or Use the Global Sort Mode**  
   - Let the user select a sort mode (e.g., "Natural Order," "Lexicographical," "Date Added") via the GUI (e.g., in a Project Settings tab).  
   - Store it in `project_state.settings["global_sort_mode"]`.  
   - On refreshing any list in the UI (subjects, experiments, plugins, body parts, etc.), read this mode and call the unified sort function.

**4) Handle Context-Specific Overrides**  
   - If you need specialized sorting (e.g., grouping experiments by subject ID), do the grouping/filtering first, then pass that filtered list into `sort_items(...)`.  
   - For body parts or objects that currently have no `date_added`, either add that field or gracefully degrade to name-based sorting.

## Next Steps: Further Sorting Refinement

Below are four key steps to make sorting simpler and more consistent:

1. **Add a Shared Interface / Mixin for "Date-Added" Types**  
   - In `metadata.py`, create a small protocol/mixin (e.g., `HasDateAdded`) defining a `date_added` field (or similarly named).  
   - Have metadata classes (_MouseMetadata_, _ExperimentMetadata_, etc.) inherit or conform to this mixin so they can be automatically sorted by their date fields.

2. **Centralize Name Sorting / Display Names**  
   - Similarly, define a mixin or protocol for "HasName" if items share a `name` property.  
   - This lets us unify the logic for sorting by name (lowercased or otherwise) without writing separate lambdas for each item type.

3. **Refine `sort_manager.py` to Exploit These Interfaces**  
   - Update `sort_items(...)` so it checks if an item implements `HasDateAdded` (for date sorting) or `HasName` (for name-based sorting).  
   - If so, pick the correct key automatically, reducing code duplication in `StateManager` or `ProjectManager`.

4. **Keep `ProjectMetadata` in Mind**  
   - Double-check `ProjectMetadata` and other older fields to ensure they still align with the new global sort approach.  
   - If you plan to sort or list projects themselves, you may want a standardized `date_created`, `project_name`, or other fields that follow the same mixin approach.

By consolidating these patterns, your `get_sorted_list` method in `state_manager.py` (and any calls to sorting in `ProjectManager`) will become cleaner and more maintainable. The final objective is to **remove redundancy** and ensure your code always uses a **single approach** to sorting, for all item types.

   **→ Step 2 after global sort is complete**

   1. clean up add mouse and add experiment so they are synchrnous and can be displayed by global sort implement,
      - make sure adding a subject refreshes the subject list and displays the new subject in the list,
      - make sure there is good feedback when a subject is added to an experiment,
      - implment (superseeding global sort) sort experiments by mouse ID, by plugin type, and by date added

List data relationships

# Current Overview of Data Classes For Sorting as currently possible by global sort using current version of sort_manager.py. Core still needs to be updated to use this new sorting approach and we need consider special cases and what patterns we want to follow.

Below is a concise list of the primary data classes in **MUS1** that appear in lists and benefit from sorting by name or date. In each case, note any special considerations (e.g., fallback fields, unique ID fields).

---

## 1. `MouseMetadata`
- **Possible Sort Fields**:
  - `date_added` (Date-based sorting)
  - `id` (Unique mouse ID; can also serve as a fallback).
- **Additional Considerations:**  
  - Some pipelines sort by birth date or genotype. Generally, though, “date_added” is used for chronological listing and “id” for name-like listing.

---

## 2. `ExperimentMetadata`
- **Possible Sort Fields**:
  - `date_added` (Date the experiment was recorded/created in the system)
  - `id` (Experiment ID, often includes numbers that might need natural sorting)
- **Additional Considerations:**  
  - Some “grouping” or specialized sorts happen by `subject_id` or `type` (plugin type).  
  - A fallback is “Lexicographical / Natural Order” of the `id`.

---

## 3. `PluginMetadata`
- **Possible Sort Fields**:
  - `date_created` (When the plugin was registered or created)
  - `name` (Plugin’s display name)
- **Additional Considerations:**  
  - Typically sorted lexicographically by name for UI displays.  
  - “Date Added” might help if you want to show the newest plugins first.

---

## 4. `BodyPartMetadata`
- **Possible Sort Fields**:
  - `date_added` (When the body part was added)
  - `name` (e.g., “nose,” “tail_base”)
- **Additional Considerations:**  
  - Often displayed in forms or lists (like “master body parts”).  

---

## 5. `ObjectMetadata`
- **Possible Sort Fields**:
  - `date_added`
  - `name` (the object’s label, e.g. “Cube1”)
- **Additional Considerations:**  
  - Some projects might rely more on lexicographical ordering for object names.

---

## 6. `BatchMetadata`
- **Possible Sort Fields**:
  - `date_added`
  - Possibly `analysis_type` if you need specialized grouping.
- **Additional Considerations:**  
  - Often used in an “analysis queue” or “batch processing” UI, so chronological order by `date_added` is typical.

---

## 7. `ArenaImageMetadata`
- **Possible Sort Fields**:
  - `date` (When the image was created/recorded)
  - `path` (Lexicographical if you want to sort by file name)
- **Additional Considerations:**  
  - This might not always appear in user-facing lists, but if so, date or file name is typical.
  - most useful may be by subject ID or experiment and if labled or not
  - we need to consider future CV implementation and how to sort these images and videos and how we relate them to the experiments and subjects
---

## 8. `VideoMetadata`
- **Possible Sort Fields**:
  - `date` (When the video was recorded)
  - `path`
- **Additional Considerations:**  
  - Similar to `ArenaImageMetadata`: might be sorted by file path or date for quick chronological listing, most useful may be by subject ID or experiment and if labled or not
  - we need to consider future CV implementation and how to sort these images and videos and how we relate them to the experiments and subjects
---

## 9. `ExternalConfigMetadata`
- **Possible Sort Fields**:
  - `date` (When the config was created/last updated)
  - `path`
- **Additional Considerations:**  
  - Typically minimal usage but might be displayed if you let users manage external config files.
  _ we are not saving them atm but might need to consider this for the future

---

## Overall Strategy
- **Date-based sorting** often references fields like `date_added`, `date_created`, or `date_recorded`.  
- **Name-based sorting** typically references a `name` or `id` property, which may need natural order parsing if it mixes letters and numbers.  
- **Fallback Fields** might include `id` or `path` when no `date` or `name` is available.  
- **Consistency** is key: by applying the same protocol or mixin approach (HasDateAdded, HasName) and a unified `sort_manager.py`, each list can be sorted reliably using a single interface.
