# -*- coding: utf-8 -*-
"""A4 / A4b / A5 / A5b / A6：段落裁剪的四种情形 + 整块字符级截断。

夹具构造：直接向课程写入手写 profile.md，不经生成器——测的是注入时的防御性裁剪。
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
SAMPLES = os.path.join(PACK, "tests", "samples")
sys.path.insert(0, os.path.join(PACK, "core", "scripts"))
sys.path.insert(0, os.path.join(PACK, "tests", "fixtures"))

import profile_spec  # noqa: E402
import build as fixtures  # noqa: E402

ENV = {k: v for k, v in os.environ.items()
       if k not in ("MEMORY_ROOT", "RECALLOOP_COURSE", "STUDYLOOP_COURSE")}
ENV["PYTHONIOENCODING"] = "utf-8"

MARK = profile_spec.MARK


def run(args, cwd):
    return subprocess.run([sys.executable, MEMPY] + args, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=ENV)


def make_profile(per_para_chars: int, total_paras: int = 4) -> str:
    """构造手写 profile：每段若干条填充，长度可控。"""
    lines = [MARK, ""]
    for i, title in enumerate(profile_spec.PARAS[:total_paras]):
        lines.append(title)
        n = max(1, per_para_chars // 40)
        for j in range(n):
            lines.append("- 填充条目%02d：这是用于测试裁剪的完整句子。" % j)
        lines.append("")
    return "\n".join(lines)


class Trim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-trim-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _inject_with(self, text: str, extra_recent: str = "") -> str:
        root = fixtures.build("F-empty", os.path.join(self.tmp, "c"))
        l3 = os.path.join(root, "记忆", "data", "L3", "default")
        os.makedirs(l3, exist_ok=True)
        with open(os.path.join(l3, "profile.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if extra_recent:
            with open(os.path.join(l3, "recent.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(MARK + "\n" + extra_recent)
        return run(["inject"], root).stdout

    def test_a5_valid_sample_not_trimmed(self):
        with open(os.path.join(SAMPLES, "S-valid", "profile.md"), encoding="utf-8") as f:
            text = f.read()
        out = self._inject_with(text)
        for title in profile_spec.PARAS:
            self.assertIn(title, out, "S-valid 不应被裁剪")

    def test_a5b_exactly_1000_not_trimmed(self):
        text = make_profile(240)
        text = text[:999] + "\n" if len(text) > 1000 else text
        # 构造恰好 1000：用合规列表项补齐
        while len(text) < 1000:
            text = text.rstrip("\n") + "\n- 补齐条目：完整句子。\n"
        text = text[:1000]
        self.assertEqual(1000, len(text))
        out = self._inject_with(text)
        kept = [t for t in profile_spec.PARAS if t in out]
        self.assertEqual(4, len(kept), "恰好 1000 时四个段标题必须全部保留")

    def test_a6_1001_drops_exactly_one(self):
        text = make_profile(260)
        while len(text) < 1001:
            text = text.rstrip("\n") + "\n- 补齐条目：完整句子。\n"
        text = text[:1001]
        out = self._inject_with(text)
        kept = [t for t in profile_spec.PARAS if t in out]
        self.assertEqual(3, len(kept), "超 1 字符应恰丢一段")
        self.assertIn(profile_spec.PARAS[0], kept)
        self.assertNotIn(profile_spec.PARAS[3], kept)

    def test_a4_far_over_budget_keeps_top_priority(self):
        text = make_profile(700)
        out = self._inject_with(text)
        kept = [t for t in profile_spec.PARAS if t in out]
        self.assertGreaterEqual(len(kept), 1)
        self.assertIn(profile_spec.PARAS[0], kept, "最高优先段必须保留")

    def test_a4b_block_level_truncation_mark(self):
        text = make_profile(200)
        recent = "\n".join(
            "- 2026-11-2%d %s" % (i, "近期记录用于撑满整块预算。" * 40) for i in range(4))
        out = self._inject_with(text, recent)
        self.assertIn(profile_spec.TRUNC_MARK, out, "整块超预算应出现截断标记")
        # 被截的是段尾：画像段必须与源文件（去掉生成标记后的正文）逐字节相同
        body = text.replace(profile_spec.MARK, "", 1).strip()
        self.assertIn(body, out, "整块截断时 profile 内容必须保持完整")

    def test_trim_never_splits_a_line(self):
        text = make_profile(400)
        trimmed = profile_spec.trim(text, 800)
        for line in trimmed.splitlines():
            if line.startswith("- "):
                self.assertTrue(line.endswith("。"), "裁剪产生半截列表项：%r" % line[-6:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
