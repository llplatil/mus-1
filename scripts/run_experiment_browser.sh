#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Single Chinook launcher for MUS1 web + common Slurm tasks.

Examples:
  # Launch the MUS1 web app (default)
  ./scripts/run_experiment_browser.sh web --pull --install

  # Launch web via Slurm allocation (recommended for long sessions)
  ./scripts/run_experiment_browser.sh web --slurm --time 02:00:00

  # Submit retraining job (checks for idle/mix nodes first)
  ./scripts/run_experiment_browser.sh train --check-idle --follow

Web options:
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

Train options:
  --script PATH           Slurm script to submit (default: EZM U-Net from zones)
  --kind KIND             Run kind for DB indexing (default: ezm_unet)
  --check-idle            Refuse to submit unless sinfo shows idle/mix nodes for script partition
  --follow                Tail the output log after submission
  --no-follow             Do not tail output log

Notes:
  - This script assumes MUS1 is installed in conda env 'mus1-dev'.
  - It binds Streamlit to 127.0.0.1 so it is only reachable via SSH forwarding.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

subcmd="${1:-web}"
if [[ "$subcmd" == "web" || "$subcmd" == "train" ]]; then
  shift 1 || true
elif [[ "$subcmd" == "-h" || "$subcmd" == "--help" || "$subcmd" == "help" ]]; then
  usage
  exit 0
else
  # Backwards-compatible: calling without explicit "web" still works.
  subcmd="web"
fi

wdmoseq2_root="$(cd "$repo_root/../.." && pwd)"
project_path="${MUS1_PROJECT_PATH:-${wdmoseq2_root}/data}"
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

train_script=""
train_kind="ezm_unet"
train_check_idle="0"
train_follow="0"

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
    --script) train_script="$2"; shift 2 ;;
    --kind) train_kind="$2"; shift 2 ;;
    --check-idle) train_check_idle="1"; shift 1 ;;
    --follow) train_follow="1"; shift 1 ;;
    --no-follow) train_follow="0"; shift 1 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if ! git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: expected a git repo (or worktree) at: $repo_root" >&2
  exit 2
fi

if [[ "$subcmd" == "web" ]]; then
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
fi

if [[ "$subcmd" == "train" ]]; then
  if [[ -z "$train_script" ]]; then
    if [[ "$train_kind" == "ml_tracking" ]]; then
      train_script="${repo_root}/workspace/ml_tracking/slurm/run_best_centermark_plus_of_scalars_time_distance_priority_syllables_bio.slurm"
    else
      train_script="${repo_root}/workspace/dlc_ezm_open_closed/torch_ml/run_train_unet_open_closed_from_zones_augfix_sched_and_qc.slurm"
    fi
  fi
  if [[ ! -f "$train_script" ]]; then
    echo "ERROR: train script not found: $train_script" >&2
    exit 2
  fi

  # Determine partition from SBATCH header (best-effort)
  part="$(awk -F= '/^#SBATCH --partition=/{print $2}' "$train_script" | tail -1 | tr -d '[:space:]')"
  if [[ "$train_check_idle" == "1" ]]; then
    if command -v sinfo >/dev/null 2>&1; then
      out="$(sinfo -h -t idle,mix -o "%P %D %N" || true)"
      if [[ -n "$part" ]]; then
        if ! echo "$out" | awk '{print $1}' | grep -qx "$part"; then
          echo "Refusing to submit: no idle/mix nodes reported for partition: $part" >&2
          echo "sinfo -h -t idle,mix -o \"%P %D %N\"" >&2
          exit 3
        fi
      else
        if [[ -z "$out" ]]; then
          echo "Refusing to submit: sinfo returned no idle/mix nodes output." >&2
          exit 3
        fi
      fi
    else
      echo "ERROR: sinfo not available but --check-idle was requested" >&2
      exit 3
    fi
  fi

  # Create a MUS1 run folder up-front (so it's not dependent on the training conda env).
  # This run dir can store lightweight provenance even if the outputs live under the MoSeq2 workspace.
  if [[ -z "${CONDA_DEFAULT_ENV:-}" || "${CONDA_DEFAULT_ENV:-}" != "mus1-dev" ]]; then
    # shellcheck disable=SC1090
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    conda activate mus1-dev
  fi
  cd "$repo_root"
  run_json="$(PYTHONPATH="${repo_root}/src" python -m mus1.core.simple_cli runs new "${train_kind}" --project-path "${project_path}" --name "train_from_browser" --json)"
  run_dir="$(python -c 'import json,sys; print(json.loads(sys.stdin.read())["run_dir"])' <<<"$run_json")"
  run_id="$(python -c 'import json,sys; print(json.loads(sys.stdin.read())["run_id"])' <<<"$run_json")"

  submit_out="$(sbatch --export=ALL,MUS1_RUN_DIR=\"${run_dir}\",MUS1_RUN_ID=\"${run_id}\",MOSEQ2_WORKSPACE_ROOT=\"${workspace_root}\" \"$train_script\")"
  echo "$submit_out"
  jobid="$(echo "$submit_out" | awk '{print $NF}')"
  echo ""
  echo "Job id: $jobid"
  echo "MUS1 run: $run_id"
  echo "MUS1 run dir: $run_dir"
  echo "Monitor:"
  echo "  squeue -j $jobid"
  echo "  sacct -j ${jobid} --format=JobID,JobName%25,State,Elapsed,MaxRSS,AllocCPUS,NodeList%25"
  echo ""

  out_pat="$(awk -F= '/^#SBATCH --output=/{print $2}' "$train_script" | tail -1)"
  err_pat="$(awk -F= '/^#SBATCH --error=/{print $2}' "$train_script" | tail -1)"
  out_log="${out_pat//%j/$jobid}"
  err_log="${err_pat//%j/$jobid}"
  if [[ -n "$out_log" ]]; then echo "stdout log: $out_log"; fi
  if [[ -n "$err_log" ]]; then echo "stderr log: $err_log"; fi

  if [[ "$train_follow" == "1" && -n "$out_log" ]]; then
    echo ""
    echo "Tailing stdout (Ctrl+C stops tail; job continues):"
    for _ in $(seq 1 30); do
      if [[ -f "$out_log" ]]; then
        tail -n 200 -f "$out_log"
        exit 0
      fi
      sleep 1
    done
    echo "Log file did not appear yet; try: tail -f $out_log" >&2
  fi
  exit 0
fi

