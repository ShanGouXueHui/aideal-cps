#!/usr/bin/env bash

echo "== check codex auth =="
if [ -f /home/deploy/.codex/auth.json ]; then
  echo "OK: /home/deploy/.codex/auth.json exists"
else
  echo "MISSING: /home/deploy/.codex/auth.json"
fi

echo
echo "== check git remote =="
git -C /home/deploy/projects/aideal-cps remote -v || true

echo
echo "== check branch =="
git -C /home/deploy/projects/aideal-cps branch --show-current || true

echo
echo "== handoff docs =="
ls -1 /home/deploy/projects/aideal-cps/docs /home/deploy/projects/aideal-cps/memory 2>/dev/null || true
