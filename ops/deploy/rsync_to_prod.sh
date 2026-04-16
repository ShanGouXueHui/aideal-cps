#!/usr/bin/env bash
cd "$(dirname "$0")/../.." || exit 1

if [ -n "${TARGETS_FILE:-}" ]; then
  CFG="$TARGETS_FILE"
elif [ -f "ops/deploy/targets.local.env" ]; then
  CFG="ops/deploy/targets.local.env"
elif [ -f "ops/deploy/targets.env" ]; then
  CFG="ops/deploy/targets.env"
else
  echo "missing deploy target file"
  exit 1
fi

. "$CFG"

SSH_TARGET="${TARGET_SSH_HOST:-$TARGET_HOST}"
MODE="${1:-}"

if [ -z "${SSH_TARGET:-}" ] || [ -z "${TARGET_USER:-}" ] || [ -z "${TARGET_PATH:-}" ] || [ -z "${TARGET_SERVICE:-}" ]; then
  echo "deploy target config incomplete"
  echo "CFG=$CFG"
  echo "TARGET_SSH_HOST=${TARGET_SSH_HOST:-}"
  echo "TARGET_HOST=${TARGET_HOST:-}"
  echo "TARGET_USER=${TARGET_USER:-}"
  echo "TARGET_PATH=${TARGET_PATH:-}"
  echo "TARGET_SERVICE=${TARGET_SERVICE:-}"
  exit 1
fi

echo "===== LOCAL CHECK ====="
echo "user=$(whoami)"
echo "pwd=$(pwd)"
git branch --show-current
git status --short

echo
echo "===== TARGET ====="
echo "cfg=$CFG"
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
