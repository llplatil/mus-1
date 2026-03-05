#!/bin/bash
#SBATCH --job-name=workspace_db_sync
#SBATCH --partition=bio
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=/center1/WDMOSEQ2/llplatil/WDMOSEQ2/apps/mus1/logs/workspace_db_sync_%j.out
#SBATCH --error=/center1/WDMOSEQ2/llplatil/WDMOSEQ2/apps/mus1/logs/workspace_db_sync_%j.err

set -euo pipefail

# Run workspace-db-sync on local scratch to avoid slow SQLite writes over NFS.
# Copies mus1.db to $TMPDIR, runs sync, copies back.
# Paths: find repo root from submit dir (sbatch cwd) by walking up to dir containing data/ and apps/.

START_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$START_DIR"
while [[ ! -d "data" || ! -d "apps" ]]; do
  cd ..
  [[ "$(pwd)" == "/" ]] && { echo "ERROR: repo root not found from $START_DIR" >&2; exit 1; }
done
WDMOSEQ2_ROOT="$(pwd)"
PROJECT_DIR="${WDMOSEQ2_ROOT}/data"
DB_PATH="${PROJECT_DIR}/mus1.db"

mkdir -p "${WDMOSEQ2_ROOT}/apps/mus1/logs"
mkdir -p "${TMPDIR:-/tmp}/mus1_sync_$$"
WORK_DIR="${TMPDIR:-/tmp}/mus1_sync_$$"

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate mus1-dev

echo "============================================================"
echo "Workspace DB sync (local scratch)"
echo "============================================================"
echo "Started at: $(date)"
echo "Host: $(hostname)"
echo "SLURM job: ${SLURM_JOB_ID:-unknown}"
echo "Project: $PROJECT_DIR"
echo "Workspace root: $WDMOSEQ2_ROOT"
echo "Work dir (local): $WORK_DIR"
echo ""

if [[ ! -f "$DB_PATH" ]]; then
  echo "Creating empty mus1.db (none found)..."
  cd "$WDMOSEQ2_ROOT"
  python -c "
from mus1.core.schema import Database
db = Database('$DB_PATH')
db.create_tables()
"
  echo "Empty DB created."
fi

cp -a "$DB_PATH" "$WORK_DIR/mus1.db"
for f in "${DB_PATH}"-wal "${DB_PATH}"-shm; do
  [[ -f "$f" ]] && cp -a "$f" "$WORK_DIR/"
done
# Link experiment_data so sync can read it (avoids copying videos)
[[ -d "${PROJECT_DIR}/experiment_data" ]] && ln -s "${PROJECT_DIR}/experiment_data" "$WORK_DIR/experiment_data"

cd "$WDMOSEQ2_ROOT"
mus1 import workspace-db-sync \
  --project-path "$WORK_DIR" \
  --workspace-root "$WDMOSEQ2_ROOT"

echo ""
echo "Copying DB back to project..."
cp -a "$WORK_DIR/mus1.db" "$DB_PATH"
[[ -f "$WORK_DIR/mus1.db-wal" ]] && cp -a "$WORK_DIR/mus1.db-wal" "${DB_PATH}-wal"
[[ -f "$WORK_DIR/mus1.db-shm" ]] && cp -a "$WORK_DIR/mus1.db-shm" "${DB_PATH}-shm"
rm -rf "$WORK_DIR"

echo ""
echo "Finished at: $(date)"
echo "============================================================"
