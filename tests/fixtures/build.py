# -*- coding: utf-8 -*-
"""三套课程夹具的构造脚本。

按 PLAN-L3.md §3.1 的硬性规定生成：
  1. 全部文件 UTF-8 无 BOM
  2. messages.json 用 type/text/content，省略 time
  3. L1 三条记录同 sid=fixture-session，含 trn_fixture_0001
  4. 每次调用重建目标目录，不复用

夹具是动态构造（时间戳按运行时刻生成），参与基线哈希的是本脚本，不是生成物。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil

MARKER = ".study-workspace"
SID = "fixture-session"
TURN_ID = "trn_fixture_0001"

PROFILE_MARK = "<!-- generated-by: recalloop -->"

PARAS = (
    "### 目标与进度",
    "### 掌握度概览",
    "### 薄弱环节",
    "### 学习节奏",
)


def _write(path: str, text: str) -> None:
    """UTF-8 无 BOM 写入，父目录自动创建。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _iso(ts: dt.datetime) -> str:
    return ts.astimezone().isoformat()


def build_empty(dest: str) -> str:
    """F-empty：仅工作区标记。"""
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    _write(os.path.join(dest, MARKER), "")
    return dest


def build_l1(dest: str, days_ago: tuple[int, ...] = (0, 1, 2)) -> str:
    """F-l1：标记 + 3 条 L1 + path.json + messages.json。"""
    shutil.rmtree(dest, ignore_errors=True)
    mem = os.path.join(dest, "记忆")
    os.makedirs(dest, exist_ok=True)
    _write(os.path.join(dest, MARKER), "")

    now = dt.datetime.now().astimezone()
    rows = []
    for i, ago in enumerate(days_ago):
        ts = now - dt.timedelta(days=ago, minutes=i * 7)
        rows.append({
            "v": 1,
            "turn_id": TURN_ID if i == 0 else "trn_fixture_%04d" % (i + 1),
            "turn_key": "fixture-key-%d" % i,
            "scope": "default",
            "sid": SID,
            "surface": "chat",
            "started_at": _iso(ts),
            "ended_at": _iso(ts),
            "msg_ids": ["msg-%d" % i],
            "msg_count": 1,
            "excerpt": "夹具记录 %d：学习了导数定义与左右极限" % (i + 1),
        })

    l1_path = os.path.join(mem, "data", "L1", now.strftime("%Y-%m-%d") + ".jsonl")
    os.makedirs(os.path.dirname(l1_path), exist_ok=True)
    with open(l1_path, "a", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    _write(
        os.path.join(mem, "data", "state", "path.json"),
        json.dumps({"items": [
            {"id": "01", "title": "导数定义", "done": False},
            {"id": "02", "title": "左右极限", "done": True},
        ]}, ensure_ascii=False, indent=2),
    )

    # 省略 time 字段：ingest 的 600 秒新鲜度门槛会拦掉静态时间戳
    _write(
        os.path.join(dest, "messages.json"),
        json.dumps([
            {"id": "m1", "sessionID": SID, "type": "user", "text": "导数定义是什么"},
            {"id": "m2", "sessionID": SID, "type": "assistant", "content": "导数描述瞬时变化率"},
        ], ensure_ascii=False, indent=2),
    )
    return dest


def build_full(dest: str) -> str:
    """F-full：F-l1 + L2 事实 + reviews.json + 无生成标记的 profile.md。"""
    build_l1(dest)
    mem = os.path.join(dest, "记忆")
    _write(
        os.path.join(mem, "data", "L2", "default.md"),
        "- 2026-11-20 · 导数的几何意义是切线斜率 <!-- ev: %s -->\n" % TURN_ID,
    )
    _write(
        os.path.join(mem, "data", "state", "reviews.json"),
        json.dumps({
            "导数定义": {"due_at": 1, "interval": 1},
            "左右极限": {"due_at": 4102444800, "interval": 7},
        }, ensure_ascii=False, indent=2),
    )
    # 无生成标记：用于 A14 的首建保护（应被拒写）
    _write(
        os.path.join(mem, "data", "L3", "default", "profile.md"),
        "### 目标与进度\n- 手工写的内容，没有生成标记。\n",
    )
    return dest


BUILDERS = {
    "F-empty": build_empty,
    "F-l1": build_l1,
    "F-full": build_full,
}


def build(name: str, dest: str) -> str:
    if name not in BUILDERS:
        raise KeyError(name)
    return BUILDERS[name](dest)


def build_all(root: str) -> dict[str, str]:
    """在 root 下重建三套夹具，返回 name -> 路径。"""
    return {name: build(name, os.path.join(root, name)) for name in BUILDERS}


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".work")
    out = build_all(target)
    for k, v in out.items():
        print("%-8s %s" % (k, v))
