# -*- coding: utf-8 -*-
"""T0 基线测试。

CP1 要求一红一绿：
  红 —— 针对 D-1（画像无生产者），当前代码必须失败，修复后转绿。
  绿 —— 结构自检，当前必须通过，证明基线不是恒红。

红断言只依赖"画像不存在"这一事实，不依赖任何待实现的细节；
绿断言只检查静态样本的结构，不 import 尚未产出的 profile_spec。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
MEMPY = os.path.join(PACK, "core", "scripts", "mem.py")
SAMPLES = os.path.join(HERE, "samples")

sys.path.insert(0, os.path.join(HERE, "fixtures"))
import build as fixtures  # noqa: E402

ENV = {k: v for k, v in os.environ.items()
       if k not in ("MEMORY_ROOT", "RECALLOOP_COURSE", "STUDYLOOP_COURSE")}
ENV["PYTHONIOENCODING"] = "utf-8"
PARAS = (
    "### 目标与进度",
    "### 掌握度概览",
    "### 薄弱环节",
    "### 学习节奏",
)
GEN_MARK = "<!-- generated-by: recalloop -->"
EXPECTED_LEN = {"S-zero": 0, "S-skeleton": 75, "S-invalid": 115, "S-valid": 862}


def run_mem(args, cwd):
    return subprocess.run(
        [sys.executable, MEMPY] + args,
        cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=ENV,
    )


def sample(name):
    with open(os.path.join(SAMPLES, name, "profile.md"), encoding="utf-8") as f:
        return f.read()


class Baseline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-t0-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- 红
    def test_red_init_produces_profile(self):
        """D-1 红断言：init 后应存在 profile.md。当前不存在，故失败。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "c"))
        proc = run_mem(["init"], root)
        self.assertEqual(0, proc.returncode, proc.stderr)
        profile = os.path.join(root, "记忆", "data", "L3", "default", "profile.md")
        self.assertTrue(os.path.exists(profile), "init 未生成 profile.md")

    def test_red_profile_build_command(self):
        """D-1 红断言：mem.py profile --build 应可执行。当前无此子命令，故失败。"""
        root = fixtures.build("F-l1", os.path.join(self.tmp, "c"))
        proc = run_mem(["profile", "--build"], root)
        self.assertEqual(0, proc.returncode,
                         "profile 子命令不存在或失败：%s" % (proc.stderr or proc.stdout))
        profile = os.path.join(root, "记忆", "data", "L3", "default", "profile.md")
        self.assertTrue(os.path.exists(profile), "profile --build 未产出文件")

    # ---------------------------------------------------------------- 绿
    def test_green_valid_sample_structure(self):
        """S-valid 结构自检：≤1000 字符、含生成标记、四段齐全、每段有列表项。"""
        text = sample("S-valid")
        self.assertLessEqual(len(text), 1000)
        self.assertTrue(text.startswith(GEN_MARK))
        for para in PARAS:
            self.assertIn(para, text)
        for block in text.split("### ")[1:]:
            self.assertIn("- ", block, "段落无列表项：%r" % block[:20])

    def test_green_sample_lengths(self):
        """四个样本长度固定且互异，S-zero 为 0 字节。"""
        for name, n in EXPECTED_LEN.items():
            self.assertEqual(n, len(sample(name)), name)
        self.assertTrue(os.path.exists(os.path.join(SAMPLES, "S-zero", "profile.md")))

    def test_green_init_creates_tree(self):
        """产品级绿断言：init 在空课程上退出 0 且四个数据目录齐备。

        补上"非恒红"对产品通路的覆盖——前两条绿只检静态样本。
        """
        root = fixtures.build("F-empty", os.path.join(self.tmp, "c2"))
        proc = run_mem(["init"], root)
        self.assertEqual(0, proc.returncode, proc.stderr)
        for sub in ("L1", "L2", "L3", "state"):
            self.assertTrue(
                os.path.isdir(os.path.join(root, "记忆", "data", sub)),
                "缺少目录：%s" % sub,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
