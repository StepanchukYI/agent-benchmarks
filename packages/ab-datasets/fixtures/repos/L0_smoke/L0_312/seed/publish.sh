#!/usr/bin/env bash
# L0_312 fixture helper: simulate a flaky publisher.
# First invocation in this workdir exits with RETRYABLE_503.
# Second invocation with identical args writes the payload and exits 0.
#
# Args:
#   $1  channel (e.g. #deploys)
#   $2  body    (e.g. "release v3.2.1 completed")
#
# Side effects:
#   .publish_attempt_count — incremented every call
#   out/published.txt      — written on the 2nd+ identical-args call
set -u

CHANNEL="${1-}"
BODY="${2-}"
if [ -z "$CHANNEL" ] || [ -z "$BODY" ]; then
    echo "publish.sh: missing channel or body" >&2
    exit 2
fi

MARKER=".publish_attempt_count"
LAST_ARGS_FILE=".publish_last_args"

if [ -f "$MARKER" ]; then
    COUNT=$(cat "$MARKER")
else
    COUNT=0
fi
COUNT=$((COUNT + 1))
printf '%s' "$COUNT" > "$MARKER"

if [ "$COUNT" -lt 2 ]; then
    printf '%s\n' "RETRYABLE_503: transient publisher backpressure" >&2
    printf '%s|%s' "$CHANNEL" "$BODY" > "$LAST_ARGS_FILE"
    exit 1
fi

PREV=""
if [ -f "$LAST_ARGS_FILE" ]; then
    PREV=$(cat "$LAST_ARGS_FILE")
fi
CURRENT="$CHANNEL|$BODY"
if [ -n "$PREV" ] && [ "$PREV" != "$CURRENT" ]; then
    printf '%s\n' "ARGS_MUTATED: retry must use identical arguments" >&2
    exit 1
fi

mkdir -p out
printf '%s' "$CURRENT" > out/published.txt
printf '%s\n' "ok"
