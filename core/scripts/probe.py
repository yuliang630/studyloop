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


def detect_skills_dirs() -> list[str]:
    """扫家目录找已存在的 <目录>/skills，不预设 agent 名字。"""
    try:
        import install_adapters as _ia
        return _ia.candidates()
    except Exception:
        return []


def verdict_of(dirs: list[str]) -> tuple[str, str]:
    if dirs:
        return "A-skills-dir", f"找到 {len(dirs)} 个候选技能目录：用 --skills-dir 指定一个即可（不限定宿主）"
    return "D-manual", "本机没找到技能目录：先手动用 CLI，或告诉我你宿主的技能目录"


def main() -> int:
    as_json = "--json" in sys.argv
    l1_files, l1_records = count_l1()
    skills_dirs = detect_skills_dirs()
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
        "skills_dirs": skills_dirs,
        "commands_available": [
            "init", "stats", "recall", "digest", "fact-add", "fact-list",
            "verify", "forget", "inject", "ingest",
        ],
    }
    route, why = verdict_of(skills_dirs)
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
    print("== 候选技能目录（不预设宿主，实测存在才列）==")
    if skills_dirs:
        for d in skills_dirs:
            print(f"  {d}")
    else:
        print("  （没找到；用 --skills-dir 指定你宿主读技能的位置）")
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
