#!/usr/bin/env bash
# Brings this checkout to the newest commit of its upstream branch: fast-forward only, never over
# local changes, and back to the old commit if the new one fails the server's self-test.
# Exit codes (read by server/kiosk/updates.py):
#   0 updated, 10 already current, 20 not a git checkout or no upstream branch,
#   30 local changes or diverged history, 40 fetch failed, 50 self-test failed (rolled back)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 20

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git checkout"
  exit 20
fi
if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  echo "the branch has no upstream"
  exit 20
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "local changes in the checkout"
  exit 30
fi
# Never wait for a password prompt at night.
if ! GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes}" git fetch --quiet 2>&1; then
  echo "fetch failed"
  exit 40
fi

old="$(git rev-parse HEAD)"
new="$(git rev-parse '@{u}')"
if [ "$old" = "$new" ]; then
  echo "already current at ${old:0:7}"
  exit 10
fi
if ! git merge-base --is-ancestor "$old" "$new"; then
  echo "the branch history diverged"
  exit 30
fi
git merge --ff-only --quiet '@{u}' || exit 30

if ! (cd server && python3 -m kiosk --self-test); then
  # This is a deployment, not a shared branch: going back to the commit that ran is the safe state.
  git reset --quiet --hard "$old"
  echo "self-test failed, back at ${old:0:7}"
  exit 50
fi
echo "updated ${old:0:7}..${new:0:7}"
exit 0
