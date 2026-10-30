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

check status        bili status
check whoami        bili whoami
check hot           bili hot
check rank          bili rank
check search        bili search 影视飓风 -n 3
check user          bili user 946974
check user-videos   bili user-videos 946974 -n 3
check video         bili video BV1xrnz6gEVD
check subtitle      bili video BV1xrnz6gEVD -s
check comments      bili video BV1xrnz6gEVD -c
check history       bili history
check favorites     bili favorites
check watch-later   bili watch-later
check feed          bili feed
check my-dynamics   bili my-dynamics

exit "$fail"
