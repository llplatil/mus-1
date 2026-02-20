#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wdmoseq2_root="$(cd "$repo_root/../.." && pwd)"
project_path="${1:-${wdmoseq2_root}/data}"
workspace_root="${2:-/center1/WDMOSEQ2/llplatil/WDMOSEQ2/moseq2_workspace}"
run_full_metadata_sync="${RUN_FULL_METADATA_SYNC:-0}"

if [[ ! -d "$project_path" ]]; then
  echo "ERROR: project path not found: $project_path" >&2
  exit 2
fi

if [[ ! -d "$workspace_root" ]]; then
  echo "ERROR: workspace root not found: $workspace_root" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate mus1-dev

export PYTHONPATH="${repo_root}/src"

echo "Project: $project_path"
echo "Workspace: $workspace_root"
echo ""
echo "[1/3] Index latest ML tracking run"
python -m mus1.core.simple_cli import ml-tracking-runs \
  --project-path "$project_path" \
  --only-latest

echo ""
echo "[2/3] Index latest EZM U-Net run"
python -m mus1.core.simple_cli import ezm-unet-runs \
  --project-path "$project_path" \
  --workspace-root "$workspace_root" \
  --only-latest

echo ""
echo "[3/3] Optional metadata sync (index + rotarod + KPMS)"
if [[ "$run_full_metadata_sync" == "1" ]]; then
  python -m mus1.core.simple_cli import workspace-db-sync \
    --project-path "$project_path" \
    --workspace-root "$workspace_root"
else
  echo "Skipped (set RUN_FULL_METADATA_SYNC=1 to enable)."
fi

echo ""
echo "Done."
