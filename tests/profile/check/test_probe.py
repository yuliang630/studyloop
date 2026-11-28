# -*- coding: utf-8 -*-
"""T3：init 落骨架、probe 复用 profile_spec 判定、probe 在任意目录可运行。

三条要点：
  1. probe 不得 import mem（mem 模块级 require_root() 会 SystemExit）；
  2. probe 的退出码语义不变（AGENTS.md §5 要求新课程自检通过）；
  3. probe 与 mem 共用 profile_spec.validate，不写第二份"像不像画像"的判断。
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
PROBE = os.path.join(PACK, "core", "scripts", "probe.py")
sys.path.insert(0, os.path.join(PACK, "core", "scripts"))
sys.path.insert(0, os.path.join(PACK, "tests", "fixtures"))

import profile_spec  # noqa: E402
import build as fixtures  # noqa: E402

ENV = {k: v for k, v in os.environ.items()
       if k not in ("MEMORY_ROOT", "RECALLOOP_COURSE", "STUDYLOOP_COURSE")}
ENV["PYTHONIOENCODING"] = "utf-8"


def run(script, args, cwd):
    return subprocess.run([sys.executable, script] + args, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=ENV)


class Probe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-t3-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a20_import_profile_spec_anywhere(self):
        """A20：非课程目录 import profile_spec 必须无副作用、退出 0。"""
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);import profile_spec" % os.path.dirname(PROBE)],
            cwd=self.tmp, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=ENV)
        self.assertEqual(0, proc.returncode, proc.stderr)

    def test_probe_does_not_import_mem(self):
        """A20 第二半：probe 不得 import mem（用 AST，不用子串——注释里就有这句话）。"""
        import ast
        path = os.path.join(PACK, "core", "scripts", "probe.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertNotIn("mem", names, "probe 不得 import mem：%r" % sorted(names))
        self.assertIn("profile_spec", names)
        """probe 在非课程目录退出 0（AGENTS.md §5 的契约）。"""
        proc = run(PROBE, [], self.tmp)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("未定位", proc.stdout)

    def test_init_creates_skeleton(self):
        """init 落空骨架：文件存在、四个段标题齐备、校验判 skeleton。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "a"))
        self.assertEqual(0, run(MEMPY, ["init"], root).returncode)
        path = os.path.join(root, "记忆", "data", "L3", "default", "profile.md")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith(profile_spec.MARK))
        for para in profile_spec.PARAS:
            self.assertIn(para, text)
        key, _ = profile_spec.validate(text)
        self.assertEqual("skeleton", key)

    def test_init_does_not_override_existing(self):
        """init 不覆盖已有画像。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "b"))
        self.assertEqual(0, run(MEMPY, ["init"], root).returncode)
        path = os.path.join(root, "记忆", "data", "L3", "default", "profile.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(profile_spec.MARK + "\n\n### 目标与进度\n- 手工内容。\n")
        with open(path, encoding="utf-8") as f:
            before = f.read()
        run(MEMPY, ["init"], root)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(before, f.read())

    def test_probe_reports_status(self):
        """probe 复用 validate：空课程报 skeleton，build 后报 ok。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "c"))
        run(MEMPY, ["init"], root)
        out = run(PROBE, [], root).stdout
        self.assertIn("skeleton", out)
        run(MEMPY, ["profile", "--build"], root)
        out = run(PROBE, [], root).stdout
        self.assertIn("ok", out)

    def test_probe_respects_scope_env(self):
        """P8：probe 按 RECALLOOP_SCOPE 解析 scope。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "d"))
        run(MEMPY, ["init", "--scope", "x"], root)
        env = dict(ENV, RECALLOOP_SCOPE="x")
        proc = subprocess.run([sys.executable, PROBE], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(0, proc.returncode)
        self.assertIn("scope=x", proc.stdout)
        self.assertIn("skeleton", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
