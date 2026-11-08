#!/bin/bash
# Keep the Mac running with the lid closed while a scan runs, then put sleep back to normal.
#
#     sudo scripts/keep_awake_for_scan.sh
#
# Closing the lid sleeps a Mac unless it has power and an external display, and only an admin can override that.
# The setting survives restarts, so this always turns it back off: when no scan has run for GRACE_SECONDS, after
# MAX_SECONDS, or when the battery is low. If it was ever left on: sudo pmset -a disablesleep 0
set -u
GRACE_SECONDS=600        # gap allowed between scans, such as the main scan and the route pass
MAX_SECONDS=$((4 * 3600))
LOW_BATTERY=20           # percent, only checked when unplugged
POLL_SECONDS=20

if [[ $EUID -ne 0 ]]; then
  echo "Needs admin rights: sudo $0" >&2
  exit 1
fi

if [[ "${1:-}" != "--hold" ]]; then
  nohup "$0" --hold >/dev/null 2>&1 &
  disown
  echo "Lid can be closed: sleep is off until the scan finishes (at most $((MAX_SECONDS / 3600)) hours)."
  echo "Avoid closing it in a bag: the Mac stays on and gets warm."
  exit 0
fi

trap 'pmset -a disablesleep 0' EXIT
trap 'exit 0' INT TERM HUP
pmset -a disablesleep 1

started=$SECONDS
last_scan=$SECONDS
while (( SECONDS - started < MAX_SECONDS && SECONDS - last_scan < GRACE_SECONDS )); do
  pgrep -f 'bots\.pipeline' >/dev/null && last_scan=$SECONDS
  battery=$(pmset -g batt)
  if ! grep -q "AC Power" <<<"$battery"; then
    percent=$(grep -Eo '[0-9]+%' <<<"$battery" | head -1 | tr -d '%')
    (( ${percent:-100} <= LOW_BATTERY )) && exit 0
  fi
  sleep "$POLL_SECONDS"
done
