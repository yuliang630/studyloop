# -*- coding: utf-8 -*-
"""往返用例：生成器写出的文件必须通过它自己的校验器。

这是"生成器与校验器共用同一组常量"的门禁。C-5（0 字节）、C-6（段末标点）、
占位行三次矛盾，都是因为生成与校验各写一套规则；本用例在三种数据状态下
各跑一次 build → check，任何一次不一致即失败。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MEMPY = os.path.join(PACK, "core", "scripts", "mem.py")
sys.path.insert(0, os.path.join(PACK, "core", "scripts"))
sys.path.insert(0, os.path.join(PACK, "tests", "fixtures"))

import profile_spec  # noqa: E402
import build as fixtures  # noqa: E402

ENV = {k: v for k, v in os.environ.items()
       if k not in ("MEMORY_ROOT", "RECALLOOP_COURSE", "STUDYLOOP_COURSE")}
ENV["PYTHONIOENCODING"] = "utf-8"


def run(args, cwd):
    return subprocess.run([sys.executable, MEMPY] + args, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=ENV)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-rt-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, root, label):
        b = run(["profile", "--build"], root)
        self.assertEqual(0, b.returncode, "%s build 失败：%s" % (label, b.stderr))
        c = run(["profile", "--check"], root)
        self.assertEqual(0, c.returncode,
                         "%s check 失败：%s" % (label, (c.stdout or "").strip()))
        self.assertIn("profile:ok", c.stdout, label)

    def test_empty_course(self):
        """无 path.json、无 attempts：目标/掌握度/薄弱三段都是占位行。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "a"))
        self._check(root, "F-empty")

    def test_l1_only(self):
        """有 path.json、无 attempts：掌握度与薄弱两段是占位行。"""
        root = fixtures.build("F-l1", os.path.join(self.tmp, "b"))
        self._check(root, "F-l1")

    def test_with_attempts(self):
        """有作答但无薄弱环节：薄弱段是占位行，掌握度段是真实行。"""
        root = fixtures.build("F-l1", os.path.join(self.tmp, "c"))
        state = os.path.join(root, "记忆", "data", "state")
        now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(os.path.join(state, "attempts.jsonl"), "w", encoding="utf-8",
                  newline="\n") as f:
            for correct in (1.0, 1.0, 1.0):
                f.write(json.dumps({
                    "ts": now, "kp": "导数定义", "type": "procedure",
                    "correct": correct, "hints": 0, "question": "", "note": "",
                }, ensure_ascii=False) + "\n")
        self._check(root, "F-l1+attempts")

    def test_every_generated_line_is_recognized(self):
        """格式模板与校验正则必须同步：模板生成的每一行都要通过校验。"""
        samples = [
            profile_spec.GOAL_LINE.format(id="01", title="导数定义", status="未完成"),
            profile_spec.GOAL_LINE.format(id="02", title="左右极限", status="已完成"),
            profile_spec.MASTERY_LINE.format(kp="导数定义", mastery=0.82,
                                             threshold=0.95, status="未达标"),
            profile_spec.WEAK_LINE.format(kp="导数定义", correct=0.5, hints=2),
        ]
        text = profile_spec.MARK + "\n\n"
        text += profile_spec.PARAS[0] + "\n" + samples[0] + "\n" + samples[1] + "\n\n"
        text += profile_spec.PARAS[1] + "\n" + samples[2] + "\n\n"
        text += profile_spec.PARAS[2] + "\n" + samples[3] + "\n\n"
        text += profile_spec.PARAS[3] + "\n" + profile_spec.RHYTHM_LINE.format(
            days=14, active=3, count=12) + "\n"
        key, detail = profile_spec.validate(text)
        self.assertEqual("ok", key, detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
