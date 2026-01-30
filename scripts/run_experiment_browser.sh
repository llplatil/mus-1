#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run the MUS1 Streamlit experiment browser on Chinook (optionally via Slurm),
and print the matching SSH port-forward command for your laptop.

Examples:
  # Run on current host (login node or already-allocated compute node)
  ./scripts/run_experiment_browser.sh

  # Run via Slurm allocation (recommended for long sessions)
  ./scripts/run_experiment_browser.sh --slurm --time 02:00:00

  # Also update code + reinstall web deps before launching
  ./scripts/run_experiment_browser.sh --pull --install

Options:
  --project-path PATH     Path that contains mus1.db
  --workspace-root PATH   MoSeq2 workspace root
  --port PORT             Streamlit port on the remote host (default: 8502)
  --address ADDR          Bind address (default: 127.0.0.1)
  --local-port PORT       Local laptop port (default: 8503)
  --jump-host HOST        SSH jump host for port-forwarding (default: chinook04.alaska.edu)
  --user USER             SSH user (default: current $USER)
  --pull                  Run 'git pull' before launching
  --install               Run 'pip install -e \".[web]\"' before launching (in mus1-dev)

Slurm:
  --slurm                 Run the app inside an srun allocation
  --time HH:MM:SS         Slurm time (default: 02:00:00)
  --partition NAME        Slurm partition (optional)
  --account NAME          Slurm account (optional)
  --cpus N                Slurm cpus-per-task (default: 1)
  --mem MEM               Slurm memory, e.g. 4G (optional)

Notes:
  - This script assumes MUS1 is installed in conda env 'mus1-dev'.
  - It binds Streamlit to 127.0.0.1 so it is only reachable via SSH forwarding.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

project_path="${MUS1_PROJECT_PATH:-/center1/WDMOSEQ2/llplatil/WDMOSEQ2/moseq2_workspace/mus1_projects/moseq2_workspace_db}"
workspace_root="${MOSEQ2_WORKSPACE_ROOT:-/center1/WDMOSEQ2/llplatil/WDMOSEQ2/moseq2_workspace}"
port="8502"
address="127.0.0.1"
local_port="8503"
jump_host="chinook04.alaska.edu"
ssh_user="${USER}"
do_pull="0"
do_install="0"

use_slurm="0"
slurm_time="02:00:00"
slurm_partition=""
slurm_account=""
slurm_cpus="1"
slurm_mem=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --project-path) project_path="$2"; shift 2 ;;
    --workspace-root) workspace_root="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --address) address="$2"; shift 2 ;;
    --local-port) local_port="$2"; shift 2 ;;
    --jump-host) jump_host="$2"; shift 2 ;;
    --user) ssh_user="$2"; shift 2 ;;
    --pull) do_pull="1"; shift 1 ;;
    --install) do_install="1"; shift 1 ;;
    --slurm) use_slurm="1"; shift 1 ;;
    --time) slurm_time="$2"; shift 2 ;;
    --partition) slurm_partition="$2"; shift 2 ;;
    --account) slurm_account="$2"; shift 2 ;;
    --cpus) slurm_cpus="$2"; shift 2 ;;
    --mem) slurm_mem="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -d "$repo_root/.git" ]]; then
  echo "ERROR: expected a git repo at: $repo_root" >&2
  exit 2
fi

if [[ "$do_pull" == "1" ]]; then
  ( cd "$repo_root" && git pull )
fi

run_app_cmd=(
  "mus1" "web" "experiment-browser"
  "--project-path" "$project_path"
  "--workspace-root" "$workspace_root"
  "--port" "$port"
  "--address" "$address"
)

pre_cmd=()
if [[ "$do_install" == "1" ]]; then
  pre_cmd+=( "python" "-m" "pip" "install" "-e" ".[web]" )
fi

echo ""
echo "Remote host: $(hostname)"
echo "Project path: $project_path"
echo "Workspace root: $workspace_root"
echo "Streamlit bind: ${address}:${port}"
echo ""
echo "On your laptop, run:"
echo "  ssh -J ${ssh_user}@${jump_host} -L ${local_port}:localhost:${port} ${ssh_user}@$(hostname)"
echo "Then open:"
echo "  http://localhost:${local_port}"
echo ""

if [[ "$use_slurm" == "1" ]]; then
  # Friendly hint about availability before launching a new job.
  if command -v sinfo >/dev/null 2>&1; then
    echo "Slurm availability (idle/mix nodes):"
    sinfo -h -t idle,mix -o "%P %D %N" | head -20 || true
    echo ""
  fi

  srun_args=( "--nodes=1" "--ntasks=1" "--cpus-per-task=${slurm_cpus}" "--time=${slurm_time}" )
  if [[ -n "$slurm_partition" ]]; then srun_args+=( "--partition=${slurm_partition}" ); fi
  if [[ -n "$slurm_account" ]]; then srun_args+=( "--account=${slurm_account}" ); fi
  if [[ -n "$slurm_mem" ]]; then srun_args+=( "--mem=${slurm_mem}" ); fi

  echo "Launching via Slurm (foreground). Ctrl+C to stop."
  echo ""
  exec srun "${srun_args[@]}" bash -lc "
    set -euo pipefail
    source \"${HOME}/miniconda3/etc/profile.d/conda.sh\"
    conda activate mus1-dev
    cd \"${repo_root}\"
    $(if [[ ${#pre_cmd[@]} -gt 0 ]]; then printf '%q ' "${pre_cmd[@]}"; echo; fi)
    $(printf '%q ' "${run_app_cmd[@]}")
  "
else
  echo "Launching on current host (foreground). Ctrl+C to stop."
  echo ""
  # If the caller didn't activate mus1-dev, do it here.
  if [[ -z "${CONDA_DEFAULT_ENV:-}" || "${CONDA_DEFAULT_ENV:-}" != "mus1-dev" ]]; then
    # shellcheck disable=SC1090
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    conda activate mus1-dev
  fi
  cd "$repo_root"
  if [[ ${#pre_cmd[@]} -gt 0 ]]; then
    "${pre_cmd[@]}"
  fi
  exec "${run_app_cmd[@]}"
fi

