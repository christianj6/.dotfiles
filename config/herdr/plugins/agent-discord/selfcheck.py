#!/usr/bin/env python3
"""Pre-deployment selfcheck for the agent-discord plugin.

Catches the failure class that bit twice on 2026-09-05 (bot.py then
notify.py): py_compile happily compiles a module with a missing import,
but the NameError only detonates at runtime -- for notify.py that means
every herdr event hook invocation dies and notifications silently stop.
Run `python3 selfcheck.py` after ANY edit to these files; wire it into
whatever process guards deployments.
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
    print("selfcheck:", "FAILED" if failures else "all green")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
