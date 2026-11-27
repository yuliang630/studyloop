#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径解析：唯一决定"记忆库在哪"的地方。

优先级（全部都是**显式**来源，没有"随便找个地方写"的兜底）：
  1. 环境变量 MEMORY_ROOT（显式指定）
  2. 当前工作目录含 .study-workspace → <cwd>/记忆        ← 课程工作区
  3. config.json 里的 default_workspace（安装时显式配置过）
  都不成立 → 报错退出（退出码 2），不写任何地方。

设计约束：包内不写死盘符；程序目录与数据目录分离；不在课程目录之外记录任何东西。
"""

from __future__ import annotations

import json
import os
import sys

MARKER = ".study-workspace"

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))      # StudyPack\core\scripts
CORE_DIR = os.path.dirname(SCRIPTS_DIR)                        # StudyPack\core
PACK_ROOT = os.path.dirname(CORE_DIR)                          # StudyPack
CONFIG_PATH = os.path.join(PACK_ROOT, "config.json")


class NotAWorkspace(RuntimeError):
    """当前目录不是课程工作区，且没有显式指定记忆根。"""


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def try_resolve_root() -> str | None:
    """能定位就返回记忆根，定位不到返回 None（不写任何地方）。"""
    env = os.environ.get("MEMORY_ROOT")
    if env:
        return os.path.abspath(env)

    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, MARKER)):
        return os.path.join(cwd, "记忆")

    ws = load_config().get("default_workspace") or ""
    if ws and os.path.isdir(ws):
        return os.path.join(ws, "记忆")

    return None


def resolve_root() -> str:
    root = try_resolve_root()
    if root is None:
        raise NotAWorkspace(HINT)
    return root


def require_root() -> str:
    """给命令行脚本用：定位不到就打印原因并退出 2，绝不静默换一个位置写。"""
    # 只打印帮助时不校验工作区（否则在包目录里敲 --help 会先报错，很别扭）
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        return ""
    try:
        return resolve_root()
    except NotAWorkspace as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(2)


HINT = ("当前目录不是课程工作区（缺 .study-workspace），也没有设置 MEMORY_ROOT。\n"
        "        先 cd 到课程根目录；确实要用别处，就显式设置：\n"
        "          set MEMORY_ROOT=<记忆根目录>\n"
        "          python core\\scripts\\setup_config.py --workspace <课程根目录>")


def describe_source() -> str:
    if os.environ.get("MEMORY_ROOT"):
        return "env:MEMORY_ROOT"
    if os.path.exists(os.path.join(os.getcwd(), MARKER)):
        return "workspace:.study-workspace"
    if (load_config().get("default_workspace") or ""):
        return "config:default_workspace"
    return "none"


def scripts_dir() -> str:
    return SCRIPTS_DIR


def pack_root() -> str:
    return PACK_ROOT
