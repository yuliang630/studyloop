#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自检：探测本机环境与记忆库状态，给出该走哪条适配路线。

给"刚接手这个记忆库的 agent"用。先跑它，再按 verdict 选路线。
用法：
    python probe.py          # 人读格式
    python probe.py --json   # 机器读格式
"""

from __future__ import annotations

import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import paths as _paths

ROOT = _paths.try_resolve_root()          # probe 可以在任何目录跑：定位不到只报告，不报错
ROOT_SOURCE = _paths.describe_source()
DATA = os.path.join(ROOT, "data") if ROOT else ""
HOME = os.path.expanduser("~")

# harness 标记目录（存在即认为该 harness 可能在本机）
HARNESS_MARKERS = {
    "opencode": [os.path.join(HOME, ".config", "opencode")],
    "claude-code": [os.path.join(HOME, ".claude")],
    "codex": [os.path.join(HOME, ".codex")],
    "cursor": [os.path.join(HOME, ".cursor")],
    "codebuddy/workbuddy": [
        os.path.join(HOME, ".codebuddy"),
        os.path.join(HOME, ".workbuddy"),
    ],
    "deepseek-harness": [os.path.join(HOME, ".dsh"), os.environ.get("DSH_HOME", "")],
}


def read_lines(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [l for l in f.read().splitlines() if l.strip()]
    except Exception:
        return []


def count_l1() -> tuple[int, int]:
    if not DATA:
        return 0, 0
    d = os.path.join(DATA, "L1")
    if not os.path.isdir(d):
        return 0, 0
    files = 0
    records = 0
    for name in os.listdir(d):
        if name.endswith(".jsonl"):
            files += 1
            records += len(read_lines(os.path.join(d, name)))
    return files, records


def count_l2() -> int:
    if not DATA:
        return 0
    d = os.path.join(DATA, "L2")
    if not os.path.isdir(d):
        return 0
    n = 0
    for name in os.listdir(d):
        if name.endswith(".md"):
            for line in read_lines(os.path.join(d, name)):
                if re.match(r"^- \d{4}-\d{2}-\d{2} · .+ <!--\s*ev:", line):
                    n += 1
    return n


def l3_ready() -> dict:
    if not DATA:
        return {"profile": False, "recent": False}
    base = os.path.join(DATA, "L3", "default")
    return {
        "profile": os.path.exists(os.path.join(base, "profile.md")),
        "recent": os.path.exists(os.path.join(base, "recent.md")),
    }


def detect_harness() -> dict:
    found = {}
    for name, paths in HARNESS_MARKERS.items():
        for p in paths:
            if p and os.path.exists(p):
                found[name] = p
                break
    return found


def verdict_of(harness: dict) -> tuple[str, str]:
    names = set(harness)
    if "opencode" in names:
        return "A-opencode", "本机是 OpenCode，用 plugins/memory.ts（已适配）"
    if names & {"claude-code", "codebuddy/workbuddy", "deepseek-harness"}:
        return "A-hooks", "本机 agent 支持命令钩子，用 hooks.json（SessionStart→inject / Stop→ingest）"
    if "cursor" in names:
        return "D-static", "Cursor 无命令钩子：只能静态注入 rules + 手动调 CLI"
    return "D-manual", "未识别到已知 harness：先手动用 CLI，或补齐适配层"


def main() -> int:
    as_json = "--json" in sys.argv
    l1_files, l1_records = count_l1()
    report = {
        "memory_root": ROOT,
        "python": sys.version.split()[0],
        "os": sys.platform,
        "data": {
            "l1_files": l1_files,
            "l1_records": l1_records,
            "l2_facts": count_l2(),
            "l3": l3_ready(),
        },
        "harness_detected": detect_harness(),
        "commands_available": [
            "init", "stats", "recall", "digest", "fact-add", "fact-list",
            "verify", "forget", "inject", "ingest",
        ],
    }
    route, why = verdict_of(report["harness_detected"])
    report["verdict"] = {"route": route, "reason": why}

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    d = report["data"]
    print("== 记忆库自检 ==")
    print(f"根目录      {ROOT or '（未定位）'}")
    print(f"来源        {ROOT_SOURCE}")
    if not ROOT:
        print("注意        当前目录不是课程工作区，也没有设置 MEMORY_ROOT；")
        print("            插件不会在任何地方写记忆。先 cd 到含 .study-workspace 的课程目录。")
    print(f"Python      {report['python']}  ({report['os']})")
    print(f"L1          {d['l1_files']} 个文件 / {d['l1_records']} 条记录")
    print(f"L2          {d['l2_facts']} 条事实")
    print(f"L3          profile={'有' if d['l3']['profile'] else '无'}  recent={'有' if d['l3']['recent'] else '无'}")
    print()
    print("== 检测到的 harness ==")
    if report["harness_detected"]:
        for k, v in report["harness_detected"].items():
            print(f"  {k:<22} {v}")
    else:
        print("  （未识别）")
    print()
    print("== 素材解析能力 ==")
    try:
        import parsers as _p

        for name, eng in _p.capability_table():
            print(f"  {name:<18} {eng}")
    except Exception as exc:
        print(f"  （解析层不可用：{exc}）")
    print()
    print(f"== 建议路线 == {route}")
    print(f"  {why}")
    print()
    print("下一步：按 README.md 第 2 节选路线；装完跑第 5 节验收清单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
