# -*- coding: utf-8 -*-
"""A10–A13：四类样本必须得到四种判定。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MEMPY = os.path.join(PACK, "core", "scripts", "mem.py")
SAMPLES = os.path.join(PACK, "tests", "samples")
sys.path.insert(0, os.path.join(PACK, "tests", "fixtures"))

import build as fixtures  # noqa: E402

ENV = {k: v for k, v in os.environ.items()
       if k not in ("MEMORY_ROOT", "RECALLOOP_COURSE", "STUDYLOOP_COURSE")}
ENV["PYTHONIOENCODING"] = "utf-8"

CASES = (
    ("S-zero", 3, "profile:missing"),
    ("S-skeleton", 3, "profile:skeleton"),
    ("S-invalid", 1, "profile:invalid"),
    ("S-valid", 0, "profile:ok"),
)


class SampleVerdicts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-samples-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, sample):
        root = fixtures.build("F-empty", os.path.join(self.tmp, sample))
        dst = os.path.join(root, "记忆", "data", "L3", "default", "profile.md")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(SAMPLES, sample, "profile.md"), dst)
        return subprocess.run([sys.executable, MEMPY, "profile", "--check"], cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=ENV)

    def test_four_samples_four_verdicts(self):
        for sample, rc, token in CASES:
            with self.subTest(sample=sample):
                proc = self._check(sample)
                self.assertEqual(rc, proc.returncode, proc.stdout + proc.stderr)
                self.assertIn(token, proc.stdout)

    def test_verdicts_are_distinct(self):
        """四种判定必须可区分，不能有任意两种落在同一 token。"""
        got = {s: self._check(s).stdout.split()[0] for s, _, _ in CASES}
        self.assertEqual(4, len(set(got.values())), got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
