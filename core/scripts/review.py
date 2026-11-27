#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复习清单：今天该复习什么。

用法：
    python review.py due [--days 3]     # 到期与未来 N 天
    python review.py stats              # 排期概览
    python review.py reset --kp "xxx"   # 清除某知识点的排期（重来）
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srs  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def fmt(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M")


def cmd_due(args) -> int:
    now = dt.datetime.now().timestamp()
    rows = srs.due_list(now, args.days)
    if not rows:
        print("（今天没有到期的复习）")
        return 0
    print(f"{'知识点':<24} {'到期':<18} {'逾期':>6}  {'间隔':>7}  {'半衰期':>7}")
    for r in rows:
        over = f"{r['overdue_days']}天" if r["overdue_days"] > 0 else "未到期"
        print(f"{r['kp']:<24} {fmt(r['due_at']):<18} {over:>6}  {r['interval_days']:>6.2f}d  {r['halflife_days']:>6.2f}d")
    print(f"\n共 {len(rows)} 条")
    return 0


def cmd_stats(args) -> int:
    data = srs.load()
    if not data:
        print("（尚无排期记录）")
        return 0
    now = dt.datetime.now().timestamp()
    due = srs.due_list(now)
    print(f"已排期知识点 {len(data)} 个，今天到期 {len(due)} 个")
    for kp, st in sorted(data.items(), key=lambda kv: kv[1].get("due_at", 0)):
        print(f"  {kp:<24} due={fmt(st.get('due_at', 0))}  reps={st.get('reps', 0)}  "
              f"lapses={st.get('lapses', 0)}  half={st.get('halflife_days')}d")
    return 0


def cmd_reset(args) -> int:
    data = srs.load()
    if args.kp not in data:
        print(f"（没有该知识点的排期：{args.kp}）")
        return 0
    del data[args.kp]
    srs.save(data)
    print(f"已清除：{args.kp}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="review.py", description="复习清单")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("due")
    d.add_argument("--days", type=int, default=0, help="额外看未来 N 天")

    sub.add_parser("stats")

    r = sub.add_parser("reset")
    r.add_argument("--kp", required=True)

    args = p.parse_args()
    if args.cmd == "due":
        return cmd_due(args)
    if args.cmd == "stats":
        return cmd_stats(args)
    if args.cmd == "reset":
        return cmd_reset(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
