#!/usr/bin/env python3
"""Seed a live .env from a template so it can never shadow a real secret.

    python3 scripts/env-seed.py <template> <dest>

- dest missing: write the template with EVERY key line commented out
  (`KEY=` -> `#KEY=`), mode 0600. The owner un-comments and fills in, or
  appends `KEY=value`; nothing empty is ever live.
- dest present: never rewrite a value. Only an EMPTY active key (`KEY=` or
  `KEY=   # comment`) is commented out in place: it carries no secret, and in a
  higher-priority file it shadows the real one (2026-11-11: setup copied the
  Discord template, its empty DISCORD_BOT_TOKEN= hid the real token, and the
  bot never started).

Prints one line saying what it did. Never prints a value.
"""

import os
import re
import sys
from pathlib import Path

KEY_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def value_of(raw: str) -> str:
    v = raw.strip()
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        return v[1:end] if end > 0 else v[1:]
    m = re.search(r"(^|\s)#", v)
    return (v[: m.start()] if m else v).strip()


def seed_text(template: str) -> str:
    out = []
    for line in template.splitlines():
        m = KEY_LINE.match(line)
        out.append(f"{m.group(1)}#{m.group(2)}={m.group(3)}" if m else line)
    return "\n".join(out) + "\n"


def heal_text(text: str) -> tuple[str, list[str]]:
    out, fixed = [], []
    for line in text.splitlines():
        m = KEY_LINE.match(line)
        if m and not value_of(m.group(3)):
            out.append(f"{m.group(1)}#{m.group(2)}={m.group(3)}")
            fixed.append(m.group(2))
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") or not text else ""), fixed


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    template, dest = Path(argv[1]), Path(argv[2]).expanduser()
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(seed_text(template.read_text()))
        print(f"env-seed: wrote {dest} (every key commented out: fill in what you use)")
        return 0
    text = dest.read_text()
    healed, fixed = heal_text(text)
    if fixed:
        tmp = dest.with_name(dest.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(healed)
        os.replace(tmp, dest)
        print(f"env-seed: {dest}: commented out empty {', '.join(fixed)} (they shadowed real values)")
    else:
        print(f"env-seed: {dest}: ok (no empty keys)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
