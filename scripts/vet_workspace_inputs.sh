#!/usr/bin/env bash
set -euo pipefail

workspace_root="${1:-/center1/WDMOSEQ2/llplatil/WDMOSEQ2/moseq2_workspace}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

missing=0

check_file() {
  local p="$1"
  if [[ -f "$p" ]]; then
    echo "OK    $p"
  else
    echo "MISS  $p"
    missing=$((missing + 1))
  fi
}

echo "Workspace root: $workspace_root"
echo "Repo root:      $repo_root"
echo ""
echo "== Core contracts =="
check_file "${repo_root}/workspace/contracts/ml_tracking_metadata_model/index/session_index_filtered.csv"

echo ""
echo "== Rotarod =="
check_file "${workspace_root}/statistics_summaries/rotarod_reanalysis/rotarod_attempts_long_timepoint_cleaned.csv"
check_file "${workspace_root}/statistics_summaries/rotarod_reanalysis/rotarod_sessions_cleaned.csv"

echo ""
echo "== KPMS results =="
check_file "${workspace_root}/analysis_keypoint_moseq/_reruns/20260122_trim30s_ezm/ezm_kpms_trim30s_20260122_iters100/results.h5"
check_file "${workspace_root}/analysis_keypoint_moseq/nor_snapshot230_20251228/nor_kpms_20260128_iters100_states100/results.h5"
check_file "${workspace_root}/analysis_keypoint_moseq/nof_snapshot230_20251228/nof_kpms_20260128_iters100_states100/results.h5"

echo ""
echo "== MoSeq2 labels =="
check_file "${workspace_root}/analysis_balanced_genotypes_sex_expanded/_reruns/20260106_clip900_npcs10/model/final_model_only/model_nonrobust_kappa2500_npcs10_clip900_iter1000/moseq_df.csv"

echo ""
echo "== Summary =="
if [[ "$missing" -eq 0 ]]; then
  echo "All required inputs are present."
  exit 0
fi

echo "Missing required inputs: $missing"
exit 1
