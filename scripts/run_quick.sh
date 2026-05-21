#!/usr/bin/env bash
# run_quick.sh — fastest path from clone to a single live benchmark row.
#
#   scripts/run_quick.sh                # defaults: claude-sonnet-4-5 / low / L0_smoke
#   MODEL=claude-haiku-4-5 EFFORT=high scripts/run_quick.sh L0_001
#   RUNNER=mock scripts/run_quick.sh    # no API keys / no live calls
#
# Output: ~/.ab/results/<utc>-<runid>/{scores.json,trajectory.jsonl,metadata.yaml}
set -euo pipefail

RUNNER="${RUNNER:-claude-code}"
MODEL="${MODEL:-claude-sonnet-4-5}"
EFFORT="${EFFORT:-low}"
TIER="${TIER:-T0}"
SUITE="${SUITE:-L0_smoke}"
TASK="${1:-}"

cmd=(uv run ab run
  --suite "$SUITE"
  --runner "$RUNNER"
  --model "$MODEL"
  --tier "$TIER"
  --effort "$EFFORT"
)
if [[ -n "$TASK" ]]; then
  cmd+=(--task "$TASK")
fi

echo ">>> ${cmd[*]}"
"${cmd[@]}"
