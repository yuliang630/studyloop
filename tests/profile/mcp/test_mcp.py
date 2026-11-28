# -*- coding: utf-8 -*-
"""T4 / T4b：MCP 画像资源与 scope 解析。

A7：MCP 占位文案必须含一行反引号包裹的命令，该命令在 mem.py 注册表内，
    执行后确实产生画像。
A8：P8=环境变量时，非默认 scope 的画像可经资源读取。
A23：钩子层缓存按 scope 判过期（静态检查，Node 环境不在本测试范围）。
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SCRIPTS = os.path.join(PACK, "core", "scripts")
MEMPY = os.path.join(SCRIPTS, "mem.py")
PROBE = os.path.join(SCRIPTS, "probe.py")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(PACK, "tests", "fixtures"))

import build as fixtures  # noqa: E402

ENV = {k: v for k, v in os.environ.items()
       if k not in ("MEMORY_ROOT", "RECALLOOP_COURSE", "STUDYLOOP_COURSE")}
ENV["PYTHONIOENCODING"] = "utf-8"


def run(args, cwd, extra=None):
    env = dict(ENV, **(extra or {}))
    return subprocess.run([sys.executable, MEMPY] + args, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)


class McpProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl-t4-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a7_placeholder_message_has_executable_command(self):
        """清空画像 → 资源文案必须给出可执行命令，且该命令能产生画像。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "a"))
        # 先 init 建出目录与骨架，再删掉画像：目录存在、文件不存在，
        # 这才是"还没生成画像"的状态（与"scope 不存在"区分）。
        run(["init"], root)
        os.remove(os.path.join(root, "记忆", "data", "L3", "default", "profile.md"))
        env = dict(ENV, MEMORY_ROOT=os.path.join(root, "记忆"))
        code = (
            "import sys, os;"
            "sys.path.insert(0, %r);"
            "import mcp_server as m;"
            "print(m.resource_read('recalloop://profile'))" % SCRIPTS
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(0, proc.returncode, proc.stderr)
        msg = proc.stdout.strip()
        commands = re.findall(r"`([^`]+)`", msg)
        self.assertTrue(commands, "占位文案必须含反引号包裹的命令：%r" % msg)
        cmd = commands[0]
        self.assertIn("profile --build", cmd)

        # 该命令在注册表中，且执行后产生画像
        choices = run(["--help"], root).stdout
        self.assertIn("profile", choices)
        argv = shlex.split(cmd)
        argv[0] = sys.executable
        built = subprocess.run(argv, cwd=root, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env)
        self.assertEqual(0, built.returncode, built.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(root, "记忆", "data", "L3", "default", "profile.md")))

    def test_a8_env_only_scope(self):
        """P8 的真实用法：只设环境变量，不传 --scope。

        这条测的是生产端与消费端共用一个 scope 规则（paths.resolve_scope），
        而不是像之前那样用 --scope 造好文件再用 env 读。
        """
        root = fixtures.build("F-empty", os.path.join(self.tmp, "b"))
        env = dict(ENV, RECALLOOP_SCOPE="x")
        mem_env = dict(env, MEMORY_ROOT=os.path.join(root, "记忆"))

        # 生产端：init 与 build 都不带 --scope
        self.assertEqual(0, subprocess.run(
            [sys.executable, MEMPY, "init"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=env).returncode)
        self.assertEqual(0, subprocess.run(
            [sys.executable, MEMPY, "profile", "--build"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=env).returncode)

        self.assertTrue(os.path.exists(
            os.path.join(root, "记忆", "data", "L3", "x", "profile.md")),
            "env-only build 必须写进 scope=x，而不是 default")
        self.assertFalse(os.path.exists(
            os.path.join(root, "记忆", "data", "L3", "default", "profile.md")),
            "不应在 default 下残留画像")

        # 消费端：probe 与 MCP 都必须看到同一个 scope
        probe = subprocess.run([sys.executable, PROBE], cwd=root, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", env=env)
        self.assertIn("scope=x", probe.stdout)
        self.assertIn("profile=ok", probe.stdout)

        code = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "import mcp_server as m;"
            "print(m.resource_read('recalloop://profile')[:80])" % SCRIPTS
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=mem_env)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("目标与进度", proc.stdout)

    def test_a9_unknown_scope_reports_explicitly(self):
        """P8=环境变量：不存在的 scope 要明确提示，不返回 default 内容、不抛栈。"""
        root = fixtures.build("F-l1", os.path.join(self.tmp, "c"))
        run(["profile", "--build"], root)          # default 有画像
        env = dict(ENV, MEMORY_ROOT=os.path.join(root, "记忆"), RECALLOOP_SCOPE="nope")
        code = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "import mcp_server as m;"
            "print(m.resource_read('recalloop://profile'))" % SCRIPTS
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(0, proc.returncode, proc.stderr)
        out = proc.stdout
        self.assertIn("scope=nope", out)
        self.assertIn("不存在", out, "未知 scope 要明确说'不存在'，与'未生成'区分")
        self.assertNotIn("目标与进度", out, "不得回落到 default 的画像")

    def test_a9_empty_scope_reports_not_built(self):
        """scope 目录存在但没 build 过：提示"还没有画像"，与"不存在"区分。"""
        root = fixtures.build("F-empty", os.path.join(self.tmp, "d"))
        os.makedirs(os.path.join(root, "记忆", "data", "L3", "y"), exist_ok=True)
        env = dict(ENV, MEMORY_ROOT=os.path.join(root, "记忆"), RECALLOOP_SCOPE="y")
        code = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "import mcp_server as m;"
            "print(m.resource_read('recalloop://profile'))" % SCRIPTS
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("还没有画像", proc.stdout)
        self.assertIn("profile --build", proc.stdout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
