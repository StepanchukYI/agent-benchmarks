#!/bin/sh
# release.sh — tag a release and print the GHCR image URLs the deploy agent
# should pin.
#
# Usage:
#   scripts/release.sh v0.2.1
#
# What it does:
#   1. Checks the working tree is clean and on main.
#   2. Verifies the tag doesn't already exist locally or on origin.
#   3. Creates an annotated tag on HEAD.
#   4. Pushes the tag to origin (this triggers .github/workflows/build-images.yml).
#   5. Prints the image URLs the deploy agent should set in infra/.env.
#
# Does NOT publish images itself — that's GitHub Actions' job. Does NOT push
# to main. Does NOT modify any files.

set -eu

usage() {
    echo "usage: $0 <tag>"
    echo "  e.g. $0 v0.2.1"
    exit 2
}

[ $# -eq 1 ] || usage
TAG="$1"

case "$TAG" in
    v[0-9]*) ;;
    *)
        echo "error: tag must start with 'v' followed by a digit (got '$TAG')" >&2
        exit 2
        ;;
esac

REPO_OWNER="stepanchukyi"
SERVER_IMAGE="ghcr.io/${REPO_OWNER}/agent-benchmarks-ab-server"
LEADERBOARD_IMAGE="ghcr.io/${REPO_OWNER}/agent-benchmarks-ab-leaderboard"

# Sanity checks.
if [ -n "$(git status --porcelain)" ]; then
    echo "error: working tree is dirty — commit or stash first" >&2
    git status --short >&2
    exit 1
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "warning: not on main (on '$CURRENT_BRANCH'). Continue? [y/N]"
    read -r REPLY
    case "$REPLY" in
        y|Y) ;;
        *) echo "aborted."; exit 1 ;;
    esac
fi

if git rev-parse "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "error: tag '$TAG' already exists locally" >&2
    exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "error: tag '$TAG' already exists on origin" >&2
    exit 1
fi

SHA="$(git rev-parse HEAD)"

echo "Creating tag $TAG on $SHA..."
git tag -a "$TAG" -m "release $TAG"

echo "Pushing tag $TAG to origin..."
git push origin "refs/tags/$TAG"

cat <<EOF

Tag $TAG pushed.

GitHub Actions is now building and publishing images. Watch the run:
  https://github.com/StepanchukYI/agent-benchmarks/actions/workflows/build-images.yml

Once it goes green, the deploy agent can pin to either:

  # Pinned by release tag (rolls forward only on the next release)
  IMAGE_TAG=$TAG

  # Pinned by commit SHA (immutable, reproducible — preferred for prod)
  IMAGE_TAG=sha-$SHA

Image URLs:
  $SERVER_IMAGE:$TAG
  $SERVER_IMAGE:sha-$SHA
  $LEADERBOARD_IMAGE:$TAG
  $LEADERBOARD_IMAGE:sha-$SHA

Deploy with:
  # On the homelab, edit infra/.env to set IMAGE_TAG, then:
  docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env pull
  docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env up -d
EOF
