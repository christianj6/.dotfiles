#!/usr/bin/env python3
"""Pre-deployment selfcheck for the agent-discord plugin.

Catches the failure class that bit twice on 2026-09-05 (bot.py then
notify.py): py_compile happily compiles a module with a missing import,
but the NameError only detonates at runtime -- for notify.py that means
every herdr event hook invocation dies and notifications silently stop.
Run `python3 selfcheck.py` after ANY edit to these files; wire it into
whatever process guards deployments.

`--live` (what workspace-up runs) adds the checks that matter at runtime:
the token resolves, every live project's channel resolves to its agent, and
Discord accepts the token. `--env-file=PATH` replaces the .env files read
(repeatable; for proving the empty-token failure). Never prints a secret.
"""

import ast
import builtins
import py_compile
import sys
from pathlib import Path

MODULES = ["common.py", "notify.py", "bot.py"]

# names provided by the runtime, not by imports
RUNTIME_GLOBALS = {"__file__", "__name__", "__doc__"}


def unresolved_names(path: str) -> list[str]:
    tree = ast.parse(Path(path).read_text())
    defined = set(dir(builtins)) | RUNTIME_GLOBALS
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.Global):
            defined.update(node.names)
    return sorted(
        {
            n.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in defined
        }
    )


def live_check(env_files: "list[Path] | None" = None, connect: bool = True) -> int:
    """What the static check cannot see (it said "all green" on 2026-11-11 while
    the bot could not start): the token resolves, every channel of a live
    project resolves back to that project's agent, and Discord accepts the
    token. Never prints a secret: only "set"/"missing" and HTTP statuses."""
    import json
    import os
    import urllib.error
    import urllib.request

    sys.path.insert(0, str(Path(__file__).parent))
    import common

    failures = 0
    if env_files is not None:
        for k in ("DISCORD_BOT_TOKEN", "DISCORD_ALLOWLIST_USER_IDS"):
            os.environ.pop(k, None)
    common.load_env(env_files)
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    where = common.CONFIG_DIR / ".env"
    if token:
        print("PASS token: DISCORD_BOT_TOKEN resolves")
    else:
        print(f"FAIL token: DISCORD_BOT_TOKEN resolves to nothing - the bot cannot start "
              f"(run: echo 'DISCORD_BOT_TOKEN=...' >> {where})")
        failures += 1
    if os.environ.get("DISCORD_ALLOWLIST_USER_IDS", "").strip():
        print("PASS allowlist: set")
    else:
        print(f"FAIL allowlist: DISCORD_ALLOWLIST_USER_IDS empty - nobody can relay "
              f"(run: echo 'DISCORD_ALLOWLIST_USER_IDS=<your id>' >> {where})")
        failures += 1

    # the lookup that broke: channel label -> live agent, for every live project
    agents = common.herdr_agents()
    channels = common.load_channels()["channels"]
    live = common.label_map_of(agents)
    projects = {common.sanitize_label(Path(cwd).name) for _, cwd in live.values()}
    dormant = 0
    for label in sorted(channels):
        a = common.resolve_agent(label, agents)
        if a is None:
            if label in projects or any(lbl == label for lbl, _ in live.values()):
                print(f"FAIL channel #{label}: its project is live but no agent resolves")
                failures += 1
            else:
                dormant += 1
            continue
        print(f"PASS channel #{label} -> {a.get('name') or a.get('pane_id')} ({a.get('agent')})")
    for pane, (lbl, cwd) in sorted(live.items()):
        if lbl not in channels:
            print(f"INFO no channel yet for #{lbl} ({pane}): the bot provisions it once running")
    if dormant:
        print(f"INFO {dormant} channel(s) for projects with no live agent (replies there say so)")

    if connect:
        if not token:
            print("FAIL connect: skipped, no token")
            failures += 1
        else:
            req = urllib.request.Request("https://discord.com/api/v10/users/@me",
                                         headers={"Authorization": f"Bot {token}",
                                                  "User-Agent": "DiscordBot (herdr-agent-discord, 1)"})
            try:
                with urllib.request.urlopen(req, timeout=10) as res:
                    me = json.loads(res.read())
                print(f"PASS connect: Discord accepts the token (bot {me.get('username', '?')})")
            except urllib.error.HTTPError as e:
                print(f"FAIL connect: Discord answered {e.code}" + (" - token rejected" if e.code == 401 else ""))
                failures += 1
            except Exception as e:
                print(f"FAIL connect: no answer from Discord ({type(e).__name__})")
                failures += 1
    return failures


def main() -> int:
    failures = 0
    for mod in MODULES:
        try:
            py_compile.compile(mod, doraise=True)
            print(f"PASS compile {mod}")
        except Exception as exc:
            print(f"FAIL compile {mod}: {exc}")
            failures += 1
            continue
        missing = unresolved_names(mod)
        if missing:
            print(f"FAIL names {mod}: unresolved {missing} (missing import?)")
            failures += 1
        else:
            print(f"PASS names {mod}")
    if "--live" in sys.argv:
        env = [Path(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--env-file=")] or None
        failures += live_check(env, connect="--no-connect" not in sys.argv)
    print("selfcheck:", "FAILED" if failures else "all green")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
