#!/bin/bash
# Launcher for the agent-discord bridge bot (herdr [[startup]] hook).
# Prefers the setup.sh-managed venv (discord.py is the one non-stdlib
# dependency); notify.py never needs it (stdlib urllib only).
set -u
VENV_PY="${HERDR_DISCORD_VENV_PYTHON:-$HOME/.herdr-discord-venv/bin/python}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "$VENV_PY" ]; then
    exec "$VENV_PY" "$DIR/bot.py"
fi

echo "[agent-discord] venv python not found at $VENV_PY -- bot not started" >&2
echo "[agent-discord] one-time setup: python3 -m venv ~/.herdr-discord-venv && ~/.herdr-discord-venv/bin/pip install discord.py" >&2
echo "[agent-discord] (notifications via the [[events]] hook still work without the bot)" >&2
exit 1
