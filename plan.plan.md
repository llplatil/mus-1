<!-- e33e0a56-aae0-472f-a26d-2ec2a4093b7b 4baaf662-6556-4cd0-8c33-9477d48443b1 -->
# MUS1: Lab-Centric Sharing, Wizard Modes, and Minimal Cleanups

## Decisions (confirmed)

- Single shared library root per lab; required when using labs (not optional).
- Wizard Start Fresh deletes entire config root and resets root pointer.
- If user skips lab, default to local projects under default root.
- For peer-hosted shared folders (not always-on servers), sharing is “activated” (reachable and writable) before use; when offline, the UI shows shared library status = offline.

## Revised TODOs (based on current implementation)

- Done
  - [x] Wizard: Start Fresh vs Edit Existing and wipe old configs
  - [x] Remote scanner: use SshJobProvider/SshWslJobProvider; remove raw ssh subprocess
  - [x] Settings: Designate Shared Library action; per-lab library save; global shared root save
  - [x] LabView: Lab Library page (recordings + subjects) with link-only add to project
  - [x] ProjectView: Quick action to open Lab Library and preselect active lab
  - [x] GUI services: remove undefined repos usage; route via ProjectManagerClean

- Lab Shared Library Root & Activation
  - [ ] Treat per-lab storage root as the lab shared library root (authoritative); add `sharing_mode` (always_on | peer_hosted) and status (online/offline)
  - [ ] SetupService/Lab settings: persist `sharing_mode`, compute status from reachability + write test
  - [ ] Settings/LabView: show status badge; warn if offline
  - [ ] Workers view: bind to lab shared root and show online/offline

- Storage Precedence & Discovery (Enforce)
  - [ ] Enforce storage precedence everywhere: project.shared_root → lab.shared_root → global.shared_root
  - [ ] ProjectDiscoveryService: ensure precedence and filter when lab shared is offline (peer_hosted)
  - [ ] Project/Lab UI: add actionable hint when filter mismatches results (empty lists)

- Dev UX & Boundaries
  - [ ] Replace QMessageBox with navigation log in dev builds (project creation/switching, shared root set/move, targets scan/stage)
  - [ ] Enforce Qt facade in GUI imports; add import-linter contract

- Experiments ↔ Videos integration
  - [ ] Implement experiment↔video repository methods; wire to PluginManager and ExperimentView

- Metadata Grid (read/selection only for now)
  - [ ] Adopt `MetadataGridDisplay` where dropdowns are unwieldy (subjects/experiments lists); keep double-click activation

- Documentation
  - [ ] ARCHITECTURE_CURRENT: lab-shared root mandatory; activation for peer-hosted; precedence; wizard modes
  - [ ] ROADMAP: move precedence/activation to High Priority; mark done items
  - [ ] LAUNCH/README: filter behavior, Qt facade rule, wizard modes, lab shared status/activation

- Logging root usage
  - [ ] Prefer configured root for logs post-setup in services/main (avoid unconditional resolve)
