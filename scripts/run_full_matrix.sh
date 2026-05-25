#!/usr/bin/env bash
# run_full_matrix.sh — sweep (model × prompt × effort) over all 104 L0 tasks.
#
# Required env:
#   CLAUDE_CODE_OAUTH_TOKEN, ZAI_AUTH_TOKEN, MINIMAX_AUTH_TOKEN

set -uo pipefail   # NO -e — single failed ab run must not kill the matrix sweep
export COLUMNS=200 # prevent Rich console line-wrap in piped output

MODELS="${MODELS:-claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5 glm-4.6 MiniMax-M2}"
PROMPTS="${PROMPTS:-vanilla karpathy operator-rules}"
EFFORTS="${EFFORTS:-low high}"
TIER="${TIER:-T0}"
SUITE="${SUITE:-L0_smoke}"
SKIP_DONE="${SKIP_DONE:-0}"

if [[ -z "${TASKS:-}" ]]; then
  TASKS=$(ls packages/ab-datasets/ab_datasets/L0_foundation/L0_*.yaml | xargs -n1 basename | sed 's/-.*//' | sort -u | tr '\n' ' ')
fi

modeltag() {
  case "$1" in
    claude-opus-*)   echo "opus" ;;
    claude-sonnet-*) echo "sonnet" ;;
    claude-haiku-*)  echo "haiku" ;;
    glm-*|GLM-*)     echo "glm" ;;
    MiniMax-*)       echo "minimax" ;;
    *) echo "$1" | tr '[:upper:]' '[:lower:]' ;;
  esac
}

vendor_args() {
  case "$1" in
    glm-*|GLM-*)
      echo "--vendor zhipu --env ANTHROPIC_AUTH_TOKEN=${ZAI_AUTH_TOKEN:-MISSING}"
      ;;
    MiniMax-*)
      echo "--vendor minimax --env ANTHROPIC_AUTH_TOKEN=${MINIMAX_AUTH_TOKEN:-MISSING}"
      ;;
    *) echo "" ;;
  esac
}

prompt_args() {
  local p="$1"
  if [[ "$p" = "vanilla" ]]; then
    echo ""
  else
    local md="/tmp/ab-prompts/${p}.md"
    if [[ -f "$md" ]]; then
      echo "--claude-md $md --prompt-label $p"
    else
      echo ""
    fi
  fi
}

total=0; done=0; skipped=0

for model in $MODELS; do
  for prompt in $PROMPTS; do
    for effort in $EFFORTS; do
      total=$((total+1))
      mtag=$(modeltag "$model")
      out_root="$HOME/.ab/results-${mtag}-${prompt}-${effort}"

      if [[ "$SKIP_DONE" = "1" && -d "$out_root" ]]; then
        # Count only runs from the current matrix window (date prefix 20260524T21+
        # or later). Older runs from prior sessions don't count toward "complete".
        new_runs=$(ls "$out_root" 2>/dev/null | grep -E "^(20260524T21[0-9]{2}|20260524T2[2-9]|20260525)" | wc -l | tr -d ' ')
        if [[ "$new_runs" -ge 104 ]]; then
          echo "SKIP  $model / $prompt / $effort  (new=$new_runs already ≥104)"
          skipped=$((skipped+1))
          continue
        fi
      fi

      mkdir -p "$out_root"
      vargs=$(vendor_args "$model")
      pargs=$(prompt_args "$prompt")

      ts=$(date -u +%H:%M:%S)
      echo "[$ts] START  $model / $prompt / $effort"

      task_n=0
      for task in $TASKS; do
        task_n=$((task_n+1))
        # shellcheck disable=SC2086
        line=$(uv run ab run --suite "$SUITE" --task "$task" --runner claude-code \
          --model "$model" --tier "$TIER" --effort "$effort" \
          --results-root "$out_root" \
          $vargs $pargs 2>&1 | grep -E "^(pass|fail)" | head -1 || echo "ERR")
        echo "  [$task_n/104] $line"
      done

      ts2=$(date -u +%H:%M:%S)
      echo "[$ts2] DONE   $model / $prompt / $effort"
      done=$((done+1))
    done
  done
done

echo ""
echo "=== SUMMARY ==="
echo "total combos: $total"
echo "done: $done"
echo "skipped: $skipped"
