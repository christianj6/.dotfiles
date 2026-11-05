#!/usr/bin/env python3
"""Tests for omp-peer's sender tag (docs/task-message-tags.md, tk-b32624856c72).

Run: python3 config/herdr/skills/herdr-workstreams/test_peer.py
setup.sh installs only peer.py (as ~/.local/bin/omp-peer); this file stays in the repo.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("peer", HERE / "peer.py")
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)

AGENTS = [
    {"agent": "omp", "name": "omp-v35-wdp9", "pane_id": "wD:p9", "cwd": "/r/.dotfiles"},
    {"agent": "claude", "name": "claude-v2-wdpa", "pane_id": "wD:pA", "cwd": "/r/.dotfiles"},
    {"agent": "omp", "name": "omp-v35-wdp5", "pane_id": "wD:p5", "cwd": "/r/bro"},
    {"agent": "codex", "name": "codex-1", "pane_id": "wD:pX", "cwd": "/r/bro"},
]


def name_of(cwd):
    """project_of without git: the folder name, leading dot dropped."""
    return os.path.basename(cwd).lstrip(".")


def tag(from_role, pane):
    return peer.sender_tag(from_role, pane, AGENTS, project=name_of)


class SenderTag(unittest.TestCase):
    def test_1_an_omp_pane_is_the_coordinator(self):
        self.assertEqual(tag(None, "wD:p9"), ("[from:coordinator project:dotfiles id:omp-v35-wdp9]", "tagged"))
        self.assertEqual(tag(None, "wD:p5")[0], "[from:coordinator project:bro id:omp-v35-wdp5]")

    def test_a_claude_pane_is_a_worker(self):
        self.assertEqual(tag(None, "wD:pA")[0], "[from:worker project:dotfiles id:claude-v2-wdpa]")

    def test_1_from_overrides_the_role(self):
        self.assertEqual(tag("owner", "wD:p9")[0], "[from:owner project:dotfiles id:omp-v35-wdp9]")
        self.assertEqual(tag("harness", "wD:pA")[0], "[from:harness project:dotfiles id:claude-v2-wdpa]")

    def test_from_owner_outside_any_agent_pane(self):
        with mock.patch.object(peer.os, "getcwd", lambda: "/r/.dotfiles"):
            self.assertEqual(peer.sender_tag("owner", None, AGENTS, project=name_of)[0],
                             "[from:owner project:dotfiles id:cli]")

    def test_no_sender_and_no_from_sends_untagged(self):
        t, why = tag(None, None)
        self.assertIsNone(t)
        self.assertIn("--from", why)
        t, why = tag(None, "wD:pX")                    # a kind with no default role
        self.assertIsNone(t)
        self.assertIn("codex", why)
        self.assertEqual(tag("worker", "wD:pX")[0], "[from:worker project:bro id:codex-1]")

    def test_the_tag_is_what_the_plugin_reads(self):
        """One sender, one receiver: every tag omp-peer can write must parse as
        a tag in lifeview's prompt_provenance."""
        lspec = importlib.util.spec_from_file_location(
            "lifeview", HERE.parent.parent / "plugins" / "lifeview-fallback" / "lifeview.py")
        lv = importlib.util.module_from_spec(lspec)
        lspec.loader.exec_module(lv)
        want = {"owner": "owner", "coordinator": "agent", "worker": "agent", "bro": "agent", "harness": "machinery"}
        for role in peer.ROLES:
            text = peer.tagged("Round 3: docs/x.md", tag(role, "wD:p9")[0])
            self.assertEqual(lv.prompt_provenance({"prompt": text}), want[role], text)


class NoDoubleTag(unittest.TestCase):
    T = "[from:coordinator project:dotfiles id:omp-v35-wdp9]"

    def test_the_tag_is_its_own_first_line(self):
        self.assertEqual(peer.tagged("read docs/x.md", self.T), self.T + "\nread docs/x.md")

    def test_2_already_tagged_text_goes_out_unchanged(self):
        for text in ("[from:owner project:bro id:me] fix it", "  [from:worker project:x id:y]\nhi",
                     "[from:anything at all]"):
            self.assertEqual(peer.tagged(text, self.T), text)

    def test_untagged_without_a_tag_is_unchanged(self):
        self.assertEqual(peer.tagged("hi", None), "hi")


class SendPath(unittest.TestCase):
    """main() end to end with herdr faked: what is typed, and the delivery needle."""

    def run_main(self, argv, pane="wD:p9", transcript=None):
        sent = []

        def fake_herdr(*args):
            if args[:2] == ("agent", "list"):
                return 0, json.dumps({"result": {"agents": AGENTS}}), ""
            if args[:2] == ("agent", "get"):
                a = next(x for x in AGENTS if args[2] in (x["name"], x["pane_id"]))
                return 0, json.dumps({"result": {"agent": dict(a, agent_session={"value": "sid"})}}), ""
            if args[:2] == ("agent", "prompt"):
                sent.append(args[3])
                if transcript is not None:
                    transcript.write_text(json.dumps({"type": "queue-operation", "operation": "enqueue",
                                                      "content": args[3]}) + "\n")
                return 0, "", ""
            return 1, "", "unexpected"

        out = io.StringIO()
        env = dict(os.environ, HERDR_PANE_ID=pane) if pane else {k: v for k, v in os.environ.items() if k != "HERDR_PANE_ID"}
        with mock.patch.object(peer, "herdr", fake_herdr), mock.patch.object(peer, "project_of", name_of), \
                mock.patch.object(sys, "argv", ["omp-peer", *argv]), mock.patch.dict(os.environ, env, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()) as err:
            peer.main()
        return sent, out.getvalue(), err.getvalue()

    def test_1_dry_run_prints_the_tagged_text_and_sends_nothing(self):
        sent, out, _ = self.run_main(["send", "claude-v2-wdpa", "read docs/x.md", "--dry-run"])
        self.assertEqual(sent, [])
        self.assertEqual(out, "[from:coordinator project:dotfiles id:omp-v35-wdp9]\nread docs/x.md\n")
        _, out, _ = self.run_main(["send", "x", "fix it", "--from", "owner", "--dry-run"])
        self.assertTrue(out.startswith("[from:owner project:dotfiles id:omp-v35-wdp9]\n"), out)

    def test_untagged_send_warns(self):
        _, out, err = self.run_main(["send", "x", "hi", "--dry-run"], pane=None)
        self.assertEqual(out, "hi\n")
        self.assertIn("UNTAGGED", err)

    def test_a_claude_target_is_confirmed_from_its_own_transcript(self):
        """The coordinator -> Claude dispatch (the misattributed path) must go
        through omp-peer, so omp-peer must confirm on a claude target too: a
        message typed mid-turn lands as a queue entry first."""
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "-r--dotfiles"
            proj.mkdir()
            f = proj / "sid.jsonl"
            f.write_text("")
            with mock.patch.object(peer, "CLAUDE_PROJECTS", Path(d)), mock.patch.object(peer, "POLL_SECONDS", 0.01):
                sent, out, _ = self.run_main(["send", "claude-v2-wdpa", "read docs/task-x.md and go",
                                              "--confirm-timeout", "2"], transcript=f)
        self.assertEqual(sent, ["[from:coordinator project:dotfiles id:omp-v35-wdp9]\nread docs/task-x.md and go"])
        self.assertEqual(out.strip(), f"delivered {f}")

    def test_entry_text_reads_claude_shapes(self):
        self.assertEqual(peer.entry_text({"message": {"role": "user", "content": "plain"}}), "plain")
        self.assertEqual(peer.entry_text({"type": "queue-operation", "content": "queued"}), "queued")
        self.assertEqual(peer.entry_text({"message": {"content": [{"type": "text", "text": "omp"}]}}), "omp")


if __name__ == "__main__":
    unittest.main()
