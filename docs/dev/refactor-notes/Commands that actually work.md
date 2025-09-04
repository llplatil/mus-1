# MUS1 CLI - Commands That Actually Work

## Core Commands
```bash
mus1 status                    # works lp - Show system status and loaded lab/project state
mus1 --version                 # works lp - Show version and exit
mus1 clear-state               # works lp - Clear persistent CLI application state
```

## Scan Commands (Video Discovery)
```bash
mus1 scan videos [ROOTS...]    # Recursively scan roots for video files, stream JSON lines (path, hash)
mus1 scan dedup INPUT_FILE     # Remove duplicate hashes and attach start_time (ISO-8601)
```

## Project Commands (Project Management)
```bash
mus1 project create NAME       # Create a new MUS1 project
mus1 project list              # List available MUS1 projects
mus1 project add-videos PROJ_PATH LIST_FILE  # Register unassigned videos from JSON lines
mus1 project set-shared-root PROJ_PATH ROOT  # Configure project's shared storage root
mus1 project move-to-shared PROJ_PATH        # Move project to shared storage
mus1 project scan-and-move PROJ_PATH [ROOTS...]  # Scan, dedup, move into media/, register unassigned
mus1 project stage-to-shared PROJ_PATH LIST_FILE DEST_SUBDIR  # Stage off-shared files into shared storage
mus1 project ingest PROJ_PATH [ROOTS...]     # Single-command ingest: scan→dedup→split, then stage+register
mus1 project import-supported-3rdparty PROJ_PATH [PLUGIN]  # Import via installed plugin
mus1 project import-third-party-folder PROJ_PATH SRC_DIR   # Import third-party folder with provenance
mus1 project media-index PROJ_PATH           # Index loose media in media/ into per-recording folders
mus1 project media-assign PROJ_PATH          # Interactively assign unassigned media to subjects/experiments
mus1 project remove-subjects PROJ_PATH       # Remove subjects from project
mus1 project associate-lab PROJ_PATH LAB_ID  # Associate project with lab
mus1 project lab-status PROJ_PATH            # Show lab association status
mus1 project cleanup-copies PROJ_PATH        # Cleanup redundant copies by policy
```

## Assembly Commands (Plugin-driven Project Assembly)
```bash
mus1 project assembly list                    # works lp
mus1 project assembly list-actions PLUGIN     # List actions for specific plugin
mus1 project assembly run PROJ_PATH [PLUGIN] [ACTION]  # Run assembly action
```

## Lab Commands (Lab-level Configuration)
```bash
mus1 lab create NAME TARGET_PATH              # works - Create new lab configuration
mus1 lab list                                 # works - List available lab configurations
mus1 lab load LAB_ID                          # works - Load lab configuration (persists between commands)
mus1 lab associate PROJ_PATH LAB_ID           # Associate project with lab
mus1 lab status                               # works - Show current lab status (shows loaded lab)
mus1 lab add-worker --name NAME --ssh-alias ALIAS # works - Add worker to lab (persists)
mus1 lab add-credential ALIAS                 # Add SSH credentials to lab
mus1 lab add-target NAME KIND ROOT...         # Add scan target to lab
mus1 lab projects                             # List projects associated with lab
mus1 lab activate LAB_ID                      # Activate lab with storage check
mus1 lab configure-storage [OPTIONS]          # Configure shared storage
mus1 lab add-tracked-genotype GENE_NAME       # Add genotype to lab tracking
mus1 lab add-tracked-treatment TREATMENT_NAME # Add treatment to lab tracking
mus1 lab add-tracked-experiment-type EXP_TYPE # Add experiment type to lab tracking
mus1 lab remove-tracked-genotype GENE_NAME    # Remove genotype from tracking
mus1 lab remove-tracked-treatment TREATMENT   # Remove treatment from tracking
mus1 lab remove-tracked-experiment-type TYPE  # Remove experiment type from tracking
mus1 lab list-tracked                         # List all tracked items in lab
```

## Genotype Commands (Genotype Management)
```bash
mus1 genotype add-to-lab --gene GENE --allele ALLELE...     # Add genotype to lab
mus1 genotype add-to-project --gene GENE --allele ALLELE... # Add genotype to project
mus1 genotype accept-lab-tracked GENE_NAMES... --project PROJ  # Accept lab genotypes for project
mus1 genotype track GENE_NAME --project PROJ                 # Add gene to tracked list
mus1 genotype list --project PROJ | --lab LAB_ID             # List genotypes
mus1 genotype push-to-lab GENE_NAME --project PROJ           # Push project genotype to lab
mus1 genotype track-exp-type EXP_TYPE --project PROJ         # Track experiment type
mus1 genotype track-treatment TREATMENT --project PROJ       # Track treatment
mus1 genotype untrack-treatment TREATMENT --project PROJ     # Remove treatment from tracking
mus1 genotype accept-lab-tracked-treatments TREATMENT... --project PROJ  # Accept lab treatments
mus1 genotype list-treatments --project PROJ | --lab LAB_ID  # List treatments
mus1 genotype push-treatment-to-lab TREATMENT --project PROJ # Push treatment to lab
mus1 genotype push-exp-type-to-lab EXP_TYPE --project PROJ   # Push experiment type to lab
mus1 genotype list-exp-types --project PROJ | --lab LAB_ID   # List experiment types
```

## Plugin Commands (Plugin Management)
```bash
mus1 plugins list                    # List installed MUS1 plugins
mus1 plugins install PACKAGE         # Install plugin package via pip
mus1 plugins uninstall PACKAGE       # Uninstall plugin package via pip
```

## Setup Commands (Per-user Configuration)
```bash
mus1 setup shared --path PATH        # Configure shared projects root
mus1 setup labs --path PATH          # Configure labs root directory
mus1 setup projects --path PATH      # Configure local projects root
```

## Worker Commands (Remote Execution)
```bash
mus1 workers run PROJ_PATH --name WORKER_NAME COMMAND...  # Run command on lab worker
```

## Deprecated Commands (DO NOT USE)
- `mus1 workers list|add|remove|detect-os` - Use `mus1 lab` commands instead
- `mus1 targets list|add|remove` - Use `mus1 lab` commands instead
- `mus1 credentials-set|credentials-list|credentials-remove` - Use `mus1 lab` commands instead

## Quick Start Workflow
```bash
# 1. Setup (first time only)
mus1 setup shared --path /path/to/shared/projects
mus1 setup labs --path /path/to/labs/configs
mus1 setup projects --path /path/to/local/projects

# 2. Create lab and project
mus1 lab create "MyLab" /path/to/labs/mylab.yaml
mus1 lab activate mylab
mus1 project create myproject

# 3. Scan and ingest videos
mus1 scan videos /path/to/videos > scan_results.jsonl
mus1 scan dedup scan_results.jsonl > deduped.jsonl
mus1 project ingest myproject deduped.jsonl

# 4. Assign media to subjects/experiments
mus1 project media-assign myproject

# 5. Manage genotypes/treatments
mus1 genotype add-to-lab --gene ATP7B --allele WT Het KO
mus1 genotype track ATP7B --project myproject
```

## Notes
- Most commands require a project path or lab context
- Use `--help` with any command for detailed options
- JSON output available with `--json` flag for scripting
- Progress bars shown by default, disable with `--quiet`
- Lab state persists between CLI commands - load a lab once and it stays loaded
- Multi-layer persistence: CLI state + lab configuration files ensure state survives
- Use `mus1 clear-state` to reset CLI application state (lab config files remain)