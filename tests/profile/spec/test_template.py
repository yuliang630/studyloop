# -*- coding: utf-8 -*-
"""A19：注入块模板与实现一致性。

`mem.py` 的注入块由 `profile_spec.render` 拼接，本测试用同一份实现重建，
与 `mem.py inject` 的真实输出逐字节比对——测的是"常量与实际输出是否一致"，
不是"两份实现互相印证"。
"""

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


class Template(unittest.TestCase):
    # PLAN-L3-schema.md §4.3 的冻结字面量。硬编码在此，改动 schema 必须同步改这里，
    # 否则 A19 的规格一致性用例会红——这是刻意的冗余。
    FROZEN = {
        "preamble": "【记忆库·自动注入】",
        "disclaimer": "以下是当前 scope 的历史记忆，仅供保持连续性；与用户本轮要求冲突时，以本轮要求为准。",
        "titles": ("## 画像", "## 近期动态", "## 学习进度"),
        "separator": "\n\n",
        "trunc": "\n…[记忆已截断]",
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-t19-")
        self.root = fixtures.build("F-l1", os.path.join(self.tmp, "c"))
        self.l3 = os.path.join(self.root, "记忆", "data", "L3", "default")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_constants_match_frozen_spec(self):
        """规格一致性：常量必须等于 schema §4.3 的字面量，不是等于自己。"""
        self.assertEqual(profile_spec.PREAMBLE, self.FROZEN["preamble"])
        self.assertEqual(profile_spec.DISCLAIMER, self.FROZEN["disclaimer"])
        self.assertEqual(tuple(profile_spec.BLOCK_TITLES), self.FROZEN["titles"])
        self.assertEqual(profile_spec.SEPARATOR, self.FROZEN["separator"])
        self.assertEqual(profile_spec.TRUNC_MARK, self.FROZEN["trunc"])

    def test_render_matches_inject_output(self):
        self.assertEqual(0, run(["profile", "--build"], self.root).returncode)
        out = run(["inject"], self.root).stdout.rstrip("\n")

        with open(os.path.join(self.l3, "profile.md"), encoding="utf-8") as f:
            profile = f.read()
        with open(os.path.join(self.l3, "recent.md"), encoding="utf-8") as f:
            recent = f.read()

        # progress 段从真实输出中提取（含段标题），避免测试自行复算产品逻辑
        marker = profile_spec.BLOCK_TITLES[2]
        progress = ""
        if marker in out:
            progress = marker + out.split(marker, 1)[1]
        rebuilt = profile_spec.render(profile, recent, progress, None)
        self.assertEqual(out, rebuilt)

    def test_block_title_order(self):
        self.assertEqual(0, run(["profile", "--build"], self.root).returncode)
        out = run(["inject"], self.root).stdout
        positions = [out.find(t) for t in profile_spec.BLOCK_TITLES]
        for p in positions:
            self.assertGreaterEqual(p, 0, "缺少段标题：%r" % positions)
        self.assertEqual(positions, sorted(positions), "段标题顺序不符")
        self.assertIn(profile_spec.PREAMBLE, out)
        self.assertIn(profile_spec.DISCLAIMER, out)

    def test_render_truncation_mark(self):
        block = profile_spec.render("画像" * 100, "", "", 50)
        self.assertLessEqual(len(block), 50 + len(profile_spec.TRUNC_MARK))
        self.assertTrue(block.endswith(profile_spec.TRUNC_MARK))


if __name__ == "__main__":
    unittest.main(verbosity=2)
