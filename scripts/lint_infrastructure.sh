#!/usr/bin/env bash
set -euo pipefail
actionlint
mapfile -t shell_files < <(git ls-files --cached --others --exclude-standard '*.sh')
if [ "${#shell_files[@]}" -gt 0 ]; then
  shellcheck "${shell_files[@]}"
fi
python3 -m compileall -q scripts tests app-release/v1
while IFS= read -r source; do
  node --check "$source"
done < <(git ls-files --cached --others --exclude-standard '*.js')
docker compose -f compose.yml config --quiet
python3 scripts/update_release_manifest.py --check
