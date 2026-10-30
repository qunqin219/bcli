#!/usr/bin/env bash
# Read-only smoke test for bcli. Requires a logged-in credential.
set -uo pipefail

fail=0
check() {
  local name="$1"; shift
  local out
  out="$("$@" 2>&1)"
  if printf '%s' "$out" | grep -q '"ok": true'; then
    printf 'PASS  %s\n' "$name"
  else
    printf 'FAIL  %s\n      %s\n' "$name" "${out:0:300}"
    fail=1
  fi
}

check status        bcli status
check whoami        bcli whoami
check hot           bcli hot
check rank          bcli rank
check search        bcli search 影视飓风 -n 3
check user          bcli user 946974
check user-videos   bcli user-videos 946974 -n 3
check video         bcli video BV1xrnz6gEVD
check subtitle      bcli video BV1xrnz6gEVD -s
check comments      bcli video BV1xrnz6gEVD -c
check history       bcli history
check favorites     bcli favorites
check watch-later   bcli watch-later
check feed          bcli feed
check my-dynamics   bcli my-dynamics

exit "$fail"
