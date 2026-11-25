#!/usr/bin/env bash
# Desktop launcher entry for hitl/console/console.py: a terminal window runs the console (closing it ends the
# console: the simulation is stopped and the HITL owner shut down), the page opens in the browser.
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
# CPU pinning is the console's own (isolated CPUs of this machine, if any: see console.py)
"$(./runbridge where python)" -B hitl/console/console.py "$@"
code=$?
if [ "$code" -ne 0 ]; then  # a normal close shuts the window; a problem keeps it open to be read
    echo
    read -rp "按 Enter 關閉這個視窗（結束碼 $code）" _
fi
exit "$code"
