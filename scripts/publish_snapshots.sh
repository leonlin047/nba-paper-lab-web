#!/usr/bin/env bash
# Publish generated facts from a separate worktree; never reset the analysis tree.
set -euo pipefail
snapshot_dir="$(mktemp -d)"
files=("$@")
for file in "${files[@]}"; do
  if [ -f "data/$file" ]; then cp "data/$file" "$snapshot_dir/$file"; fi
done
analysis_head="$(git rev-parse HEAD)"
for attempt in 1 2 3; do
  git fetch origin main
  changed="$(git diff --name-only "$analysis_head" origin/main -- scripts/ tests/ .github/workflows/ platform.js platform.css index.html data/private-model-readiness.json)"
  if [ -n "$changed" ]; then
    echo 'Source changed during collection; the newer refresh will publish.'
    exit 0
  fi
  publish_dir="$(mktemp -d)"
  git worktree add --detach "$publish_dir" origin/main
  git -C "$publish_dir" config user.name 'github-actions[bot]'
  git -C "$publish_dir" config user.email '41898282+github-actions[bot]@users.noreply.github.com'
  for file in "${files[@]}"; do
    if [ -f "$snapshot_dir/$file" ]; then
      cp "$snapshot_dir/$file" "$publish_dir/data/$file"
      git -C "$publish_dir" add "data/$file"
    fi
  done
  if git -C "$publish_dir" diff --cached --quiet; then echo 'No snapshot changes'; exit 0; fi
  git -C "$publish_dir" commit -m 'data: refresh verified forecasts and independent result ledgers'
  if git -C "$publish_dir" push origin HEAD:main; then exit 0; fi
  # Worktrees are job-local backups; runner cleanup removes them at job end.
done
exit 1
