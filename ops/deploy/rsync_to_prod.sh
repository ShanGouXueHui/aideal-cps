#!/usr/bin/env bash
cd "$(dirname "$0")/../.." || exit 1

TARGETS_FILE="${TARGETS_FILE:-ops/deploy/targets.env}"
if [ ! -f "$TARGETS_FILE" ]; then
  echo "missing targets file: $TARGETS_FILE"
  exit 1
fi

. "$TARGETS_FILE"

SSH_TARGET="${TARGET_SSH_HOST:-$TARGET_HOST}"
MODE="${1:-}"

echo "===== LOCAL CHECK ====="
echo "user=$(whoami)"
echo "pwd=$(pwd)"
git branch --show-current
git status --short

echo
echo "===== TARGET ====="
echo "ssh_target=$SSH_TARGET"
echo "user=$TARGET_USER"
echo "path=$TARGET_PATH"
echo "service=$TARGET_SERVICE"

echo
echo "===== RSYNC ${MODE:---apply} ====="
if [ "$MODE" = "--dry-run" ]; then
  rsync -az --delete --dry-run --info=stats2,progress2 \
    --exclude-from=ops/deploy/rsync.exclude \
    -e "ssh" \
    ./ "${TARGET_USER}@${SSH_TARGET}:${TARGET_PATH}/"
else
  rsync -az --delete --info=stats2,progress2 \
    --exclude-from=ops/deploy/rsync.exclude \
    -e "ssh" \
    ./ "${TARGET_USER}@${SSH_TARGET}:${TARGET_PATH}/"
fi
