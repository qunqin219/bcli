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
check doctor        bili doctor
check bangumi       bili bangumi 33378
check bangumi-rank  bili bangumi-rank -n 3
check user-articles bili user-articles 946974 -n 2
check collections   bili collections 946974 -n 2
check notifications bili notifications
check unread        bili unread
check comments      bili comments BV1xrnz6gEVD -n 3
check subtitle-srt  bili subtitle-srt BV1xrnz6gEVD
check batch-list    bili batch BV1GxsX6YEuP --list
check ass           bili danmaku-export BV1xrnz6gEVD --format ass -n 3

exit "$fail"
