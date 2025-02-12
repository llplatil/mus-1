# MUS1 Refactoring / Rewrite Notes

## Objectives
- Consolidate repeated code.
- Switch or confirm logging approach (confirm whether to keep custom logging in `utils` or use Python's built-in logging).
- Unify the GUI approach (decide if `main_window.py` should be replaced with a single entry point, or if we keep a multi-window design).
- Restructure the `core` folder to ensure a cleaner architecture, matching the updated architecture doc.
- Resolve the duplicate "Mus1" folder issue by ensuring we have one source-of-truth directory on this branch.

## Proposed Steps
1. **Set up new repo structure**: 
   - Create a single `mus1` folder with subfolders `core`, `gui`, `utils`, `docs`.
   - Move or rename any duplicates carefully and test imports.

2. **Decide on logging**:
   - If retaining `mus1/utils/logging_config.py`, remove duplication and ensure it is used consistently.
   - Alternatively, remove it in favor of direct usage of Python's logging library in each module.

3. **GUI merging**:
   - Evaluate whether a single `MainWindow` logic is sufficient or if we want to keep specialized windows like `project_view.py` as a separate concern.  
   - Possibly move "splash screen" and "project selection" to a dedicated function or small module, while the main application code remains in `main_window.py`.

4. **Metadata**:
   - Keep the current pydantic-based `metadata.py` from your latest version.  
   - Optionally rename or remove the old, dataclasses-based `metadata.py` to avoid confusion.

5. **Plugins**:
   - Confirm the plugin approach: each experiment type (NOR, OpenField, etc.) will remain as submodels (Pydantic) or become separate classes?

## Notes
- For older code references, keep a local copy of the old folder or a separate branch (e.g., `archive/old-mus1`) so you never lose it but don't clutter your new structure.
- Open a Pull Request on GitHub from your new `refactor-core` branch once you have an initial commit. This helps track code reviews and changes in a safer environment than pushing commits directly to `main`.
- Commit frequently and push to the remote branch. That way you can create or update your PR and see a diff.

--- 

Example: Final ProjectState Settings in `core/metadata.py`

         class ProjectState(BaseModel):
            version: str = "0.1.0"
            last_modified: datetime = Field(default_factory=datetime.now)

            settings: Dict[str, Any] = Field(
               default_factory=lambda: {
                     "global_frame_rate": 60,
                     "global_frame_rate_enabled": False,  # turned off initially
                     "body_parts": [],
                     "active_body_parts": [],
                     "tracked_objects": []
               }
            )

            subjects: Dict[str, MouseMetadata] = Field(default_factory=dict)
            experiments: Dict[str, ExperimentMetadata] = Field(default_factory=dict)
            batches: Dict[str, BatchMetadata] = Field(default_factory=dict)
            arena_images: Dict[str, ArenaImageMetadata] = Field(default_factory=dict)
            experiment_videos: Dict[str, VideoMetadata] = Field(default_factory=dict)
            external_configs: Dict[str, ExternalConfigMetadata] = Field(default_factory=dict)

            project_metadata: Optional[ProjectMetadata] = None

def create_project(self, project_root: Path, project_name: str) -> None:
    ...
    new_state = ProjectState(project_metadata=new_metadata)
    self.state_manager._project_state = new_state
    self._current_project_root = project_root
    logger.info("New project created with empty subjects, experiments, batches.")
    self.save_project()

# MUS1 Core Refactor Notes

## ProjectManager  
- We updated `add_experiment()` to ensure that multiple validations occur:
  1. The referenced mouse exists in `ProjectState.subjects`.
  2. The mouse is allowed to do the requested `experiment_type` (if non-empty set).
  3. The user can optionally assign a session_stage or link a video/image.

- Linking arena images or videos updates both directions:
  - The experiment gets its `arena_image_path` or `video` reference.
  - The metadata for that image or video now includes the experiment's ID, so browsing the media can tell which experiments it's associated with.

## Additional Validations
- We introduced `allowed_experiment_types` in `MouseMetadata` to handle future logic about which experiments a mouse can perform. You can keep the set empty to allow all experiments by default, or treat an empty set as meaning "none allowed." Adjust as needed.

## Next Steps
- If advanced session-stage logic or types exist, consider adding more specific validation in `add_experiment()` or via Pydantic validators in `ExperimentMetadata`.
- If a mouse can only participate in certain stages, add that logic similarly.