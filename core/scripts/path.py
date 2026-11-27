#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识点路径：从课程文件解析出顺序，判断"下一步学什么"。

用法：
    python path.py init [--from "课程\\00-学习路线.md"]
    python path.py list
    python path.py next
    python path.py done --id 01
    python path.py undo --id 01

数据：记忆\\data\\state\\path.json

解析来源按优先级：
  1. 显式 --from 指定的 markdown
  2. 课程目录下的 课程\\00-学习路线.md
  3. 找不到就报错，不猜
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as _paths  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SOURCE = os.path.join("课程", "00-学习路线.md")

# | 01 | 认识 ComfyUI 与你的机器 | ... |
ROW = re.compile(r"^\|\s*(\d{1,2})\s*\|\s*([^|]+?)\s*\|")
# - [x] 01 认识 ComfyUI 与你的机器
CHECK = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(\d{1,2})\s*[-—·\s]+\s*(.+?)\s*$")


def state_path() -> str:
    d = os.path.join(_paths.require_root(), "data", "state")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "path.json")


def load() -> dict:
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"v": 1, "source": "", "items": []}


def save(data: dict) -> None:
    p = state_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def parse_markdown(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            rows.append({"id": m.group(1).zfill(2), "title": m.group(2).strip(), "done": False, "done_at": None})
            continue
        c = CHECK.match(line)
        if c:
            rows.append({"id": c.group(2).zfill(2), "title": c.group(3).strip(),
                         "done": c.group(1).lower() == "x", "done_at": None})
    # 表格里可能有重复（表头/分隔行不会命中），按 id 去重，保留先出现的
    seen, out = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append(r)
    return out


def cmd_init(args) -> int:
    src = args.from_ or os.path.join(os.getcwd(), DEFAULT_SOURCE)
    if not os.path.isfile(src):
        print(f"[error] 找不到课程文件：{src}", file=sys.stderr)
        print("       用 --from 指定，例如：python path.py init --from \"课程\\00-学习路线.md\"", file=sys.stderr)
        return 2
    with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    items = parse_markdown(text)
    if not items:
        print("[error] 没解析出任何课程条目。检查文件里是否有 `| 01 | 标题 |` 或 `- [ ] 01 标题`", file=sys.stderr)
        return 2
    save({"v": 1, "source": os.path.relpath(src, os.getcwd()), "items": items})
    print(f"[ok] 解析出 {len(items)} 条：")
    for it in items:
        mark = "x" if it["done"] else " "
        print(f"  [{mark}] {it['id']}  {it['title']}")
    return 0


def cmd_list(args) -> int:
    data = load()
    if not data.get("items"):
        print("（尚无路径，先跑 path.py init）")
        return 1
    cur = next((it["id"] for it in data["items"] if not it["done"]), None)
    for it in data["items"]:
        mark = "x" if it["done"] else " "
        arrow = " ←" if it["id"] == cur else ""
        print(f"  [{mark}] {it['id']}  {it['title']}{arrow}")
    return 0


def cmd_next(args) -> int:
    data = load()
    items = data.get("items") or []
    if not items:
        print("（尚无路径，先跑 path.py init）")
        return 1
    it = next((x for x in items if not x["done"]), None)
    if not it:
        print("[ok] 全部完成")
        return 0
    if args.json:
        print(json.dumps(it, ensure_ascii=False))
    else:
        print(f"{it['id']}  {it['title']}")
    return 0


def _mark(args, done: bool) -> int:
    data = load()
    items = data.get("items") or []
    target = next((x for x in items if x["id"] == args.id.zfill(2)), None)
    if not target:
        print(f"[error] 没有 id={args.id} 的课程", file=sys.stderr)
        return 2
    target["done"] = done
    target["done_at"] = None if not done else __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    save(data)
    print(f"{'已完成' if done else '已撤销'}：{target['id']}  {target['title']}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="path.py", description="知识点路径")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init")
    i.add_argument("--from", dest="from_", default=None)
    sub.add_parser("list")
    n = sub.add_parser("next")
    n.add_argument("--json", action="store_true")
    d = sub.add_parser("done")
    d.add_argument("--id", required=True)
    u = sub.add_parser("undo")
    u.add_argument("--id", required=True)

    args = p.parse_args()
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "next":
        return cmd_next(args)
    if args.cmd == "done":
        return _mark(args, True)
    if args.cmd == "undo":
        return _mark(args, False)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
