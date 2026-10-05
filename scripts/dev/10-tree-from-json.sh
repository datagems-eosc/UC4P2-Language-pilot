#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
curl -sS -X POST https://datagems-dev.scayle.es/language-pilot/tree \
  -H "Content-Type: application/json" \
  --data-binary @"${root}/runs/thematic_exploration_marriage_v014.json" \
  -o "${root}/runs/thematic_exploration_marriage_v014.tree.html"
echo "Wrote ${root}/runs/thematic_exploration_marriage_v014.tree.html"
