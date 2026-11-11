#!/usr/bin/env python3
"""Tests for scripts/workspace-up and scripts/env-seed.py (docs/task-selfhealing-setup.md):
python3 scripts/test_workspace_up.py

workspace-up runs against a FAKE daemon (a sleeper in a temp dir, matched by a
unique marker), never the owner's services.
"""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOTFILES = HERE.parent


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


wu = load("workspace_up", HERE / "workspace-up")
seed = load("env_seed", HERE / "env-seed.py")


class WorkspaceUp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.marker = "wu-test-" + uuid.uuid4().hex[:10]
        self.code = Path(self.dir.name) / "fake_daemon.py"
        self.code.write_text("import time\ntime.sleep(600)\n")
        old = time.time() - 3600
        os.utime(self.code, (old, old))
        self.piece = wu.Piece(
            self.marker, self.marker, lambda: [self.code],
            lambda: ([sys.executable, str(self.code), self.marker], Path(self.dir.name), {}))
        self.lines = []
        self.addCleanup(self.kill_all)
        self.addCleanup(self.dir.cleanup)

    def kill_all(self):
        for p in self.procs():
            try:
                os.kill(p.pid, 9)
            except ProcessLookupError:
                pass

    def procs(self):
        return [p for p in wu.processes() if self.marker in p.command]

    def run_once(self, dry=False, pieces=None):
        self.lines = []
        rc = wu.run(pieces or [self.piece], dry, out=self.lines.append)
        self.summary = next(ln for ln in self.lines if ln.startswith("workspace:"))
        return rc

    def test_starts_what_is_down_then_is_idempotent(self):
        self.assertEqual(self.procs(), [])
        self.run_once()
        first = self.procs()
        self.assertEqual(len(first), 1)
        self.assertIn("1 started", self.summary)
        self.run_once()                                   # second run: nothing to do
        self.assertEqual([p.pid for p in self.procs()], [first[0].pid])
        self.assertIn("0 started, 0 stale, 0 restarted", self.summary)
        self.assertNotIn("[", self.lines[0])              # no action noted on the piece's line

    def test_restarts_when_code_is_newer_than_the_process(self):
        self.run_once()
        old_pid = self.procs()[0].pid
        newer = self.procs()[0].started + 30              # the code changed after the process started
        os.utime(self.code, (newer, newer))
        self.run_once(dry=True)                           # dry run: says so, touches nothing
        self.assertIn("would restart", self.lines[0])
        self.assertIn("1 stale", self.summary)
        self.assertEqual([p.pid for p in self.procs()], [old_pid])
        self.run_once()
        pids = [p.pid for p in self.procs()]
        self.assertEqual(len(pids), 1)
        self.assertNotEqual(pids[0], old_pid)
        self.assertIn("1 restarted", self.summary)

    def test_no_launcher_is_named_in_the_summary(self):
        p = wu.Piece(self.marker, self.marker, lambda: [], lambda: None,
                     no_launcher=f"{self.marker}: repo unknown - put X= in the config")
        rc = self.run_once(pieces=[p])
        self.assertEqual(rc, 1)
        self.assertIn("1 need you", self.summary)
        self.assertIn("repo unknown", self.summary)

    def test_an_unhealthy_piece_names_what_the_owner_must_do(self):
        p = wu.Piece(self.marker, self.marker, lambda: [self.code],
                     lambda: ([sys.executable, str(self.code), self.marker], Path(self.dir.name), {}),
                     health=lambda started: (False, "token missing",
                                             ["discord: token missing\n      run: echo 'DISCORD_BOT_TOKEN=...' >> X"]))
        rc = self.run_once(pieces=[p])
        self.assertEqual(rc, 1)
        self.assertIn("UNHEALTHY", self.lines[0])
        self.assertIn("1 need you - discord: token missing", self.summary)
        self.assertTrue(any("run: echo 'DISCORD_BOT_TOKEN=...'" in ln for ln in self.lines))


class EnvSeed(unittest.TestCase):
    TEMPLATE = DOTFILES / "config/herdr/plugins/agent-discord/.env.example"

    def test_every_env_example_seeds_with_no_live_key(self):
        for t in DOTFILES.rglob(".env.example"):
            if ".git" in t.parts:
                continue
            text = seed.seed_text(t.read_text())
            live = [ln for ln in text.splitlines() if seed.KEY_LINE.match(ln)]
            self.assertEqual(live, [], t)

    def test_clean_home_seed_then_drop_a_token_and_the_loader_finds_it(self):
        with tempfile.TemporaryDirectory() as home:
            cfg = Path(home, ".config/herdr/plugins/config/dotfiles.agent-discord")
            dest = cfg / ".env"
            r = subprocess.run([sys.executable, str(HERE / "env-seed.py"), str(self.TEMPLATE), str(dest)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(oct(dest.stat().st_mode & 0o777), "0o600")
            root_env = Path(home, "plugin-root.env")
            root_env.write_text("DISCORD_BOT_TOKEN=from-the-plugin-root\n")
            # 1. the seed cannot shadow a token kept in the other file
            got = self.load(cfg, [dest, root_env])
            self.assertEqual(got, "from-the-plugin-root")
            # 2. the documented place: setup's copy-paste line appends to the seed
            with dest.open("a") as fh:
                fh.write("DISCORD_BOT_TOKEN=dropped-in\n")
            self.assertEqual(self.load(cfg, [dest, root_env]), "dropped-in")

    def load(self, cfg, files):
        code = ("import os, sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import common; "
                "common.load_env([Path(f) for f in sys.argv[2:]]); print(os.environ.get('DISCORD_BOT_TOKEN', ''))")
        env = {k: v for k, v in os.environ.items() if not k.startswith("DISCORD_")}
        r = subprocess.run([sys.executable, "-c", code, str(DOTFILES / "config/herdr/plugins/agent-discord"),
                            *map(str, files)], capture_output=True, text=True, env=env)
        return r.stdout.strip()

    def test_heal_comments_out_only_empty_keys(self):
        text = "A=\nB=   # required\nC=keep-me\n#D=\nE=keep # note\n"
        healed, fixed = seed.heal_text(text)
        self.assertEqual(fixed, ["A", "B"])
        self.assertEqual(healed, "#A=\n#B=   # required\nC=keep-me\n#D=\nE=keep # note\n")

    def test_seeding_never_rewrites_an_existing_value(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d, ".env")
            dest.write_text("DISCORD_BOT_TOKEN=s3cret-value-xyz\nDISCORD_ALLOWLIST_USER_IDS=\n")
            r = subprocess.run([sys.executable, str(HERE / "env-seed.py"), str(self.TEMPLATE), str(dest)],
                               capture_output=True, text=True)
            self.assertEqual(dest.read_text(), "DISCORD_BOT_TOKEN=s3cret-value-xyz\n#DISCORD_ALLOWLIST_USER_IDS=\n")
            self.assertNotIn("s3cret-value-xyz", r.stdout)                 # names keys, never values


class DiscordSelfcheck(unittest.TestCase):
    def test_empty_token_fails_and_prints_no_secret(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d, ".env")
            env_file.write_text("DISCORD_BOT_TOKEN=            # required\nDISCORD_ALLOWLIST_USER_IDS=123\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith("DISCORD_")}
            r = subprocess.run([sys.executable, "selfcheck.py", "--live", "--no-connect", f"--env-file={env_file}"],
                               cwd=DOTFILES / "config/herdr/plugins/agent-discord",
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("FAIL token: DISCORD_BOT_TOKEN resolves to nothing", r.stdout)
            self.assertIn("selfcheck: FAILED", r.stdout)
            self.assertNotIn("# required", r.stdout.split("FAIL token")[1].split("\n")[0].split("(run:")[0])


if __name__ == "__main__":
    unittest.main()
