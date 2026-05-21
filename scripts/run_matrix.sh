#!/usr/bin/env bash
# run_matrix.sh — run a (model × effort × task) matrix into a results dir.
#
#   scripts/run_matrix.sh                          # built-in defaults (sonnet+haiku × low+high × L0_001..L0_005)
#   MODELS=glm-4.6 EFFORTS=high TASKS=L0_001 scripts/run_matrix.sh
#   RUNNER=opencode MODELS=claude-sonnet-4-5 scripts/run_matrix.sh
#
# Vendor routing for claude-code: set VENDOR + ANTHROPIC_AUTH_TOKEN env.
#   VENDOR=zhipu ANTHROPIC_AUTH_TOKEN=$GLM_KEY MODELS=glm-4.6 scripts/run_matrix.sh
set -euo pipefail

RUNNER="${RUNNER:-claude-code}"
TIER="${TIER:-T0}"
SUITE="${SUITE:-L0_smoke}"

# Whitespace-separated lists (override via env).
MODELS="${MODELS:-claude-sonnet-4-5 claude-haiku-4-5}"
EFFORTS="${EFFORTS:-low high}"
TASKS="${TASKS:-L0_001 L0_002 L0_003 L0_004 L0_005}"

OUT_ROOT="${OUT_ROOT:-/tmp/ab-matrix-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_ROOT"
echo ">>> matrix results → $OUT_ROOT"

for model in $MODELS; do
  for effort in $EFFORTS; do
    for task in $TASKS; do
      args=(
        --suite "$SUITE"
        --task "$task"
        --runner "$RUNNER"
        --model "$model"
        --tier "$TIER"
        --effort "$effort"
        --results-root "$OUT_ROOT"
      )
      if [[ -n "${VENDOR:-}" ]]; then
        args+=(--vendor "$VENDOR")
        if [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" ]]; then
          args+=(--env "ANTHROPIC_AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN")
        fi
      fi
      echo ">>> ab run ${args[*]}"
      uv run ab run "${args[@]}" || echo "!!! failed: $model / $effort / $task"
    done
  done
done

echo
echo ">>> summary"
python3 -c "
import json, glob
for path in sorted(glob.glob('$OUT_ROOT/*/scores.json')):
    d = json.load(open(path))
    print(f\"{d['task_id']:<10} {d['model']:<28} pass={d['pass']!s:<5} score={d['total_score']:.3f}\")
"
