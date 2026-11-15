#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
actionlint
node .github/actions/check-workflow-security/check-workflow-security.js
mapfile -t shell_files < <(git ls-files --cached --others --exclude-standard '*.sh')
if [ "${#shell_files[@]}" -gt 0 ]; then
  shellcheck "${shell_files[@]}"
fi
python3 -m compileall -q .github/tools nginx scripts app-release
while IFS= read -r source; do
  node --check "$source"
done < <(git ls-files --cached --others --exclude-standard '*.js')
docker compose -f compose.yml config --quiet
python3 app-release/update_release_manifest.py --check
