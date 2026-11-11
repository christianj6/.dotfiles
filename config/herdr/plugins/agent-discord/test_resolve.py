#!/usr/bin/env python3
"""Tests for the Discord bridge's inbound routing (docs/issue-discord-replies-broken.md):
python3 test_resolve.py

The fake listing is herdr's real `agent list` shape on 2026-11-11 (names, pane ids,
workspaces and project folders as they were live), with cwds under a fake root.
"""

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

R = "/fake/repos"
LIVE = [
    {"pane_id": "wD:p9", "name": "omp-v36-wdp9", "agent": "omp", "workspace_id": "wD", "cwd": "/fake/home/.dotfiles"},
    {"pane_id": "wD:pA", "name": "claude-v2-wdpa", "agent": "claude", "workspace_id": "wD", "cwd": "/fake/home/.dotfiles"},
    {"pane_id": "wD:p7", "name": "omp-v36-wdp7", "agent": "omp", "workspace_id": "wD", "cwd": f"{R}/prescient"},
    {"pane_id": "wD:pC", "name": "claude-v2-wdpc", "agent": "claude", "workspace_id": "wD", "cwd": f"{R}/prescient"},
    {"pane_id": "wD:p5", "name": "omp-v36-wdp5", "agent": "omp", "workspace_id": "wD", "cwd": f"{R}/bro"},
    {"pane_id": "wD:p6", "name": "claude-v2-wdp6", "agent": "claude", "workspace_id": "wD", "cwd": f"{R}/bro"},
    {"pane_id": "wG:p1", "name": "omp-v36-wgp1", "agent": "omp", "workspace_id": "wG", "cwd": f"{R}/thor/thor-voiceai"},
    {"pane_id": "w5:p1D", "name": "omp-v36-w5p1d", "agent": "omp", "workspace_id": "w5", "cwd": f"{R}/heinzel"},
    {"pane_id": "w5:p1A", "name": "claude-v2-w5p1a", "agent": "claude", "workspace_id": "w5", "cwd": f"{R}/heinzel"},
]


def pane(label, agents=LIVE):
    a = common.resolve_agent(label, agents)
    return a and a["pane_id"]


class Resolve(unittest.TestCase):
    def test_live_labels_are_suffixed_which_is_the_bug(self):
        labels = {lbl for lbl, _ in common.label_map_of(LIVE).values()}
        self.assertEqual(labels, {"dotfiles-wD", "prescient-wD", "bro-wD", "heinzel-w5", "thor-voiceai"})

    def test_two_agent_project_plain_label_reaches_the_coordinator(self):
        for label, omp in (("dotfiles", "wD:p9"), ("prescient", "wD:p7"), ("heinzel", "w5:p1D"), ("bro", "wD:p5")):
            self.assertEqual(pane(label), omp, label)

    def test_coordinator_first_regardless_of_listing_order(self):
        self.assertEqual(pane("dotfiles", list(reversed(LIVE))), "wD:p9")

    def test_single_agent_project_plain_label(self):
        self.assertEqual(pane("thor-voiceai"), "wG:p1")

    def test_suffixed_channel_also_prefers_the_coordinator(self):
        self.assertEqual(pane("dotfiles-wD", list(reversed(LIVE))), "wD:p9")   # #dotfiles-wd, where notify posts

    def test_suffixed_label_from_an_older_layout(self):
        self.assertEqual(pane("dotfiles-w6"), "wD:p9")
        self.assertEqual(pane("thor-voiceai-w7"), "wG:p1")

    def test_a_real_hyphenated_project_is_not_folded_into_another(self):
        self.assertIsNone(pane("heinzel-exploration"))                  # no live agent: says so, never heinzel

    def test_claude_only_project_still_resolves(self):
        only = [a for a in LIVE if a["pane_id"] != "wD:p9"]
        self.assertEqual(pane("dotfiles", only), "wD:pA")

    def test_no_live_agent(self):
        self.assertIsNone(pane("telia-sms-fraud"))
        self.assertIsNone(pane("dotfiles", []))

    def test_a_stale_stored_pane_id_cannot_steer_delivery(self):
        # channels.json still says wD:p1 for #dotfiles; nothing in the inbound path reads it
        src = (Path(__file__).parent / "bot.py").read_text()
        tree = ast.parse(src)
        reads = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "get"
                 and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "pane_id"
                 and getattr(n.func.value, "id", "") == "entry"]
        self.assertEqual(reads, [])
        self.assertNotIn('"pane_id": pane_id', src)                    # reconcile no longer stores one
        self.assertEqual(pane("dotfiles"), "wD:p9")                    # resolved live, not wD:p1


class LoadEnv(unittest.TestCase):
    def test_an_empty_template_line_does_not_shadow_the_real_value(self):
        with tempfile.TemporaryDirectory() as cfg, tempfile.TemporaryDirectory() as root:
            Path(cfg, ".env").write_text("DISCORD_BOT_TOKEN=\nDISCORD_ALLOWLIST_USER_IDS=\n")
            Path(root, ".env").write_text("DISCORD_BOT_TOKEN=real-value\n")
            saved = (common.CONFIG_DIR, common.__file__, os.environ.pop("DISCORD_BOT_TOKEN", None))
            common.CONFIG_DIR, common.__file__ = Path(cfg), str(Path(root, "common.py"))
            try:
                common.load_env()
                self.assertEqual(os.environ.get("DISCORD_BOT_TOKEN"), "real-value")
            finally:
                common.CONFIG_DIR, common.__file__ = saved[0], saved[1]
                os.environ.pop("DISCORD_BOT_TOKEN", None)
                if saved[2] is not None:
                    os.environ["DISCORD_BOT_TOKEN"] = saved[2]


if __name__ == "__main__":
    unittest.main()
