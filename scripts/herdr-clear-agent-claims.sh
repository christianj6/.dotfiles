#!/bin/bash
# Clear persisted agent-session claims from herdr's session.json.
#
# WHY THIS EXISTS
# A managed integration's agent-session claim takes permanent ownership of
# a pane's agent slot. Any `claude` process that inherits a pane's
# HERDR_PANE_ID registers one -- including a one-shot `claude -p` probe run
# from that pane's shell, even if the pane's real occupant is omp. After
# that, herdr accepts omp-watch's report-agent calls with a clean "ok" and
# never applies them: the pane's sidebar status freezes at whatever state
# was live when the claim landed.
#
# Verified exhaustively 2026-09-15 (pane w6:p4, frozen at "working",
# state_change_seq 1181):
#   - report-agent from our own source            -> ok, no change
#   - report-agent from a never-used fresh source -> ok, no change
#   - release-agent --source herdr:claude         -> ok, claim persists
#   - report-agent-session (owning source, no id) -> ok, claim persists
# The claim lives at .workspaces[].tabs[].panes[].agent_session in
# ~/.config/herdr/session.json and survives server restarts. The running
# server rewrites that file periodically, so editing it while herdr runs is
# pointless -- the only reliable clear is: stop the server, strip the
# claims, start again.
#
# NON-DESTRUCTIVE ALTERNATIVE for a single pane: close and recreate just
# that pane (a new pane id carries no claim). Prefer that unless several
# panes are affected.
#
# DESTRUCTIVE: `herdr server stop` kills every pane process -- agents,
# editors, dev servers. Run this only when you are ready for that.

set -euo pipefail

SESSION_JSON="${HERDR_SESSION_JSON:-$HOME/.config/herdr/session.json}"

if [ ! -f "$SESSION_JSON" ]; then
    echo "no session file at $SESSION_JSON" >&2
    exit 1
fi

echo "Persisted agent-session claims in $SESSION_JSON:"
python3 - "$SESSION_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
found = 0
for wi, ws in enumerate(data.get("workspaces", [])):
    for ti, tab in enumerate(ws.get("tabs", [])):
        for pi, pane in enumerate(tab.get("panes", [])):
            claim = pane.get("agent_session")
            if claim:
                found += 1
                print(f"  workspaces[{wi}].tabs[{ti}].panes[{pi}]"
                      f"  source={claim.get('source')!r} agent={claim.get('agent')!r}")
print(f"  total: {found}")
PY

printf '\nThis stops the herdr server (killing ALL pane processes), strips the\nclaims, and leaves herdr stopped so you can start it again yourself.\nType CLEAR to proceed: '
read -r reply
[ "$reply" = "CLEAR" ] || { echo "aborted"; exit 0; }

backup="$SESSION_JSON.bak.$(date +%Y%m%d-%H%M%S)"
cp "$SESSION_JSON" "$backup"
echo "backup: $backup"

herdr server stop || true
# The server writes session.json on shutdown; strip AFTER it is gone.
sleep 2

python3 - "$SESSION_JSON" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
cleared = 0
for ws in data.get("workspaces", []):
    for tab in ws.get("tabs", []):
        for pane in tab.get("panes", []):
            if pane.pop("agent_session", None) is not None:
                cleared += 1
json.dump(data, open(path, "w"), indent=2)
print(f"cleared {cleared} claim(s)")
PY

echo "done -- start herdr again with: herdr"
