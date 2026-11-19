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


class DiscordReady(unittest.TestCase):
    """A healthy long-running bot is not reported as never ready (2026-11-18 false positive)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.log = Path(self.dir.name, "bridge.log")
        old, wu.BRIDGE_LOG = wu.BRIDGE_LOG, self.log
        self.addCleanup(setattr, wu, "BRIDGE_LOG", old)
        self.started = time.time() - 6 * 86400
        stamp = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
        self.ready = f"[{stamp(self.started + 4 * 86400)}] bot ready as X#1 in [\"s\"]"
        self.notified = [f"[{stamp(time.time() - 60)}] notified #c: idle (wX:p1, 130 chars)"] * 3000
        self.stamp = stamp

    def test_ready_line_far_back_in_a_busy_log_counts(self):
        self.log.write_text("\n".join([self.ready] + self.notified) + "\n")
        self.assertTrue(wu.bot_ready_since(self.started, wait=0))

    def test_ready_line_older_than_the_process_does_not(self):
        before = f"[{self.stamp(self.started - 3600)}] bot ready as X#1 in [\"s\"]"
        self.log.write_text("\n".join([before] + self.notified[:5]) + "\n")
        self.assertFalse(wu.bot_ready_since(self.started, wait=0))


class Serving(unittest.TestCase):
    """Which process is judged: the lock holder, not a hook launch in flight
    (docs/task-workspace-up-lockholder.md)."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.lock = Path(d.name, "lock")
        self.daemon = wu.Proc(100, 1000.0, "python3 x.py --daemon")      # serving since t=1000
        self.launch = wu.Proc(200, 9000.0, "python3 x.py --daemon")      # a hook launch, about to exit

    def test_lock_holder_is_judged_over_a_newer_launch(self):
        self.lock.write_text("100")
        proc, note = wu.serving([self.daemon, self.launch], self.lock)
        self.assertIs(proc, self.daemon)
        self.assertEqual(note, "lock holder; 200 launch in flight")

    def test_lock_holder_alone_needs_no_note(self):
        self.lock.write_text("100")
        self.assertEqual(wu.serving([self.daemon], self.lock), (self.daemon, ""))

    def test_dead_pid_in_the_lock_falls_back_to_the_newest_match(self):
        self.lock.write_text("4242")
        proc, note = wu.serving([self.daemon, self.launch], self.lock)
        self.assertIs(proc, self.launch)
        self.assertIn("lock names pid 4242, which is not running", note)

    def test_missing_or_garbage_lock_falls_back(self):
        for content in (None, "", "not-a-pid"):
            if content is None:
                self.lock.unlink(missing_ok=True)
            else:
                self.lock.write_text(content)
            proc, note = wu.serving([self.daemon, self.launch], self.lock)
            self.assertIs(proc, self.launch, content)
            self.assertIn("no pid in the lock file", note)

    def test_unlocked_piece_judges_the_newest_match_as_before(self):
        self.assertEqual(wu.serving([self.daemon, self.launch], None), (self.launch, ""))
        self.assertEqual(wu.serving([], self.lock), (None, ""))

    def test_every_plugin_daemon_piece_has_its_lock_and_the_services_none(self):
        locks = {p.name: p.lock for p in wu.PIECES}
        for name, plugin in (("lifeview", "lifeview-fallback"), ("discord-bot", "agent-discord"),
                             ("omp-watch", "omp-watch"), ("claude-name", "claude-name")):
            self.assertEqual(locks[name], wu.PLUGIN_STATE / f"dotfiles.{plugin}" / "lock", name)
            self.assertIn(wu.SHARED, next(p for p in wu.PIECES if p.name == name).code(), name)
        self.assertIsNone(locks["prescient"])
        self.assertIsNone(locks["bro"])


class ServingLive(unittest.TestCase):
    """End to end with fake processes: a stale lock holder behind a fresh launch."""
    setUp, kill_all, procs, run_once = WorkspaceUp.setUp, WorkspaceUp.kill_all, WorkspaceUp.procs, WorkspaceUp.run_once

    def start_fake(self):
        p = subprocess.Popen([sys.executable, str(self.code), self.marker], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(40):
            if any(x.pid == p.pid for x in self.procs()):
                return p.pid
            time.sleep(0.05)
        self.fail("fake process never appeared")

    def test_stale_holder_behind_a_launch_in_flight_is_restarted(self):
        lock = Path(self.dir.name, "lock")
        self.piece.lock = lock
        holder = self.start_fake()
        lock.write_text(str(holder))
        time.sleep(1.2)                                   # ps start times have 1 s resolution
        newer = time.time()
        os.utime(self.code, (newer, newer))               # code changed after the holder started
        time.sleep(1.2)
        launch = self.start_fake()                        # the hook launch: newer than the code
        self.run_once(dry=True)
        self.assertIn(f"pid {holder} lock holder; {launch} launch in flight", self.lines[0])
        self.assertIn("would restart", self.lines[0])
        self.assertIn("1 stale", self.summary)
        self.run_once()
        self.assertIn("1 restarted", self.summary)
        pids = [p.pid for p in self.procs()]
        self.assertEqual(len(pids), 1)                    # holder and launch both stopped, one started
        self.assertNotIn(holder, pids)
        self.assertNotIn(launch, pids)

    def test_fresh_holder_with_a_launch_in_flight_is_left_alone(self):
        lock = Path(self.dir.name, "lock")
        self.piece.lock = lock
        holder = self.start_fake()                        # code is an hour old: holder is fresh
        lock.write_text(str(holder))
        launch = self.start_fake()
        self.run_once()
        self.assertIn("0 stale, 0 restarted", self.summary)
        self.assertEqual(sorted(p.pid for p in self.procs()), sorted([holder, launch]))


class OmpPanes(unittest.TestCase):
    """An omp pane running other compaction settings than config/omp is named (issue-compaction-not-firing)."""

    def pane(self, started):
        return wu.OmpPane(4242, started, "wX:p1", "proj")

    def run_check(self, decision, started=None):
        lines = []
        started = time.time() if started is None else started
        rc = wu.run([], False, out=lines.append, omp=[self.pane(started)], decision=lambda pid, s: decision)
        return rc, lines

    def test_config_threshold_is_read_from_the_committed_config(self):
        self.assertEqual(wu.omp_threshold_config(), 500000)

    def test_window_zero_is_stale_and_needs_you(self):
        rc, lines = self.run_check((0, 0))
        self.assertEqual(rc, 1)
        self.assertIn("STALE: contextWindow 0: never compacts", lines[0])
        self.assertIn("1 omp stale, 1 need you - omp wX:p1 (proj)", lines[1])

    def test_old_threshold_is_stale(self):
        rc, lines = self.run_check((1000000, 660000))
        self.assertEqual(rc, 1)
        self.assertIn("threshold 660000 vs config 500000", lines[0])

    def test_matching_pane_is_ok(self):
        rc, lines = self.run_check((1000000, 500000))
        self.assertEqual(rc, 0, lines)
        self.assertIn("ok: window 1000000, threshold 500000", lines[0])
        self.assertIn("0 omp stale, 0 need you", lines[1])

    def test_threshold_clamped_to_a_small_window_is_ok(self):
        rc, lines = self.run_check((200000, 199999))
        self.assertEqual(rc, 0, lines)

    def test_no_turn_yet_judged_by_start_time_against_config_mtime(self):
        self.assertEqual(self.run_check(None)[0], 0)          # started now: after the config
        rc, lines = self.run_check(None, started=0)           # started at the epoch: before it
        self.assertEqual(rc, 1)
        self.assertIn("no turn logged, started", lines[0])

    def test_decision_is_read_from_the_newest_log_line_of_that_pid(self):
        with tempfile.TemporaryDirectory() as d:
            mk = lambda w, t: ('{"message":"%s","contextWindow":%d,"thresholdTokens":%d}' % (wu.OMP_DECISION, w, t))
            today = time.strftime("%Y-%m-%d")
            Path(d, f"omp.{today}.4242.log").write_text("\n".join([mk(0, 0), "not json", mk(1000000, 500000), '{"message":"other"}']) + "\n")
            Path(d, "omp.1999-01-01.4242.log").write_text(mk(7, 7) + "\n")      # recycled pid, ignored
            Path(d, f"omp.{today}.999.log").write_text(mk(9, 9) + "\n")         # other pid
            self.assertEqual(wu.omp_decision(4242, time.time() - 60, Path(d)), (1000000, 500000))
            self.assertIsNone(wu.omp_decision(5555, time.time(), Path(d)))

    def test_services_only_run_has_no_omp_section(self):
        lines = []
        wu.run([], False, out=lines.append)
        self.assertNotIn("omp stale", lines[0])


if __name__ == "__main__":
    unittest.main()
