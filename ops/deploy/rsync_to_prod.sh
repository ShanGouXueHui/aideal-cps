#!/usr/bin/env bash

. "$(dirname "$0")/targets.env"

cd ~/projects/aideal-cps || exit 1

echo "===== LOCAL CHECK ====="
echo "user=$(whoami)"
echo "pwd=$(pwd)"
git branch --show-current
git status --short

echo
echo "===== TARGET ====="
echo "host=$DEPLOY_HOST"
echo "user=$DEPLOY_USER"
echo "path=$DEPLOY_PATH"
echo "service=$DEPLOY_SERVICE"

echo
echo "===== RSYNC PREVIEW ====="
rsync -avzn --delete \
  --exclude-from=ops/deploy/rsync.exclude \
  -e "ssh" \
  ./ aideal-prod:${DEPLOY_PATH}/
