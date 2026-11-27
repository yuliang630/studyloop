#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""练习闭环：记录作答 → 计算掌握度 → 给出下一步。

与 mastery.py 的分工：
  mastery.py  纯函数（怎么算）
  practice.py 状态与记录（算谁的、算到哪一步）

一条硬规则（来自 DeepTutor policy.py）：**用了提示的作答会被记录，但不计入证据。**
所以 attempts.jsonl 里 hints>0 的行照存（可审计），计算掌握度时排除。

用法：
    python practice.py record --kp 链式法则 --type procedure --result 1
    python practice.py record --kp 链式法则 --type procedure --result 0 --hints 2
    python practice.py status --kp 链式法则
    python practice.py list
    python practice.py qualify --kp 导数定义 --note "能用自己的话讲清"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mastery import compute_mastery, gate_threshold, next_action  # noqa: E402
import srs  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import paths as _paths

ROOT = _paths.require_root()
STATE = os.path.join(ROOT, "data", "state")
ATTEMPTS = os.path.join(STATE, "attempts.jsonl")
QUALITATIVE = os.path.join(STATE, "qualitative.json")


def ensure_state() -> None:
    os.makedirs(STATE, exist_ok=True)


def load_attempts() -> list[dict]:
    if not os.path.exists(ATTEMPTS):
        return []
    rows = []
    with open(ATTEMPTS, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def append_attempt(rec: dict) -> None:
    ensure_state()
    with open(ATTEMPTS, "a", encoding="utf-8", errors="replace") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_qualitative() -> dict:
    try:
        with open(QUALITATIVE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_qualitative(data: dict) -> None:
    ensure_state()
    tmp = QUALITATIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8", errors="replace") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUALITATIVE)


def history_of(kp: str, rows: list[dict] | None = None) -> tuple[list[float], list[dict]]:
    """返回（计入证据的作答序列, 全部记录）。hints>0 不进证据。"""
    rows = rows if rows is not None else load_attempts()
    mine = [r for r in rows if r.get("kp") == kp]
    evidence = [float(r.get("correct", 0)) for r in mine if int(r.get("hints", 0) or 0) == 0]
    return evidence, mine


def status_of(kp: str, kp_type: str, rows: list[dict] | None = None) -> dict:
    evidence, mine = history_of(kp, rows)
    mastery = compute_mastery(evidence)
    q = load_qualitative().get(kp, {})
    passed_q = bool(q.get("passed"))
    res = next_action(kp_type, mastery, passed_q, visuals_ok=True)
    res.update({
        "kp": kp,
        "type": kp_type,
        "attempts_total": len(mine),
        "evidence_count": len(evidence),
        "excluded_by_hints": len(mine) - len(evidence),
        "qualitative_pass": passed_q,
    })
    return res


def cmd_record(args) -> int:
    ensure_state()
    correct = max(0.0, min(1.0, float(args.result)))
    hints = max(0, int(args.hints))
    rec = {
        "v": 1,
        "ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "kp": args.kp,
        "type": args.type,
        "correct": correct,
        "hints": hints,
        "question": args.question or "",
        "note": args.note or "",
    }
    append_attempt(rec)
    sched = srs.update_for(args.kp, correct, hints, time.time())
    res = status_of(args.kp, args.type)
    res["next_due"] = sched["due_at"]
    res["interval_days"] = sched["interval_days"]
    res["rating"] = sched["last_rating"]
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        flag = "计入证据" if hints == 0 else f"不计入证据（用了 {hints} 次提示）"
        due = dt.datetime.fromtimestamp(sched["due_at"]).astimezone().strftime("%m-%d %H:%M")
        print(f"已记录：{args.kp}  {correct:g} 分 · {flag}")
        print(f"  掌握度 {res['mastery']} / 门槛 {res['threshold']}  →  {res['action']}")
        print(f"  下次复习 {due}（间隔 {sched['interval_days']:.2f} 天，评级 {sched['last_rating']}）")
        print(f"  {res['reason']}")
    return 0


def cmd_status(args) -> int:
    rows = load_attempts()
    kps = sorted({r.get("kp") for r in rows if r.get("kp")})
    only = getattr(args, "kp", None)
    if only:
        kps = [only]
    if not kps:
        print("（尚无作答记录）")
        return 0
    out = []
    for kp in kps:
        kp_type = next((r.get("type") for r in reversed(rows) if r.get("kp") == kp), "memory")
        out.append(status_of(kp, kp_type, rows))
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    for s in out:
        mark = "✅" if s["passed"] else "○"
        print(f"{mark} {s['kp']:<16} {s['type']:<10} mastery={s['mastery']:<6} "
              f"门槛={s['threshold']}  作答={s['attempts_total']} 证据={s['evidence_count']}"
              + (f"（提示排除 {s['excluded_by_hints']}）" if s["excluded_by_hints"] else ""))
    return 0


def cmd_qualify(args) -> int:
    data = load_qualitative()
    data[args.kp] = {
        "passed": True,
        "note": args.note or "",
        "ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    save_qualitative(data)
    print(f"已记录定性通过：{args.kp}（概念/设计类不看准确率，看能否讲清）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="practice.py", description="练习闭环")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="记录一次作答")
    r.add_argument("--kp", required=True, help="知识点标识")
    r.add_argument("--type", required=True, choices=["memory", "procedure", "concept", "design"])
    r.add_argument("--result", required=True, help="得分：1 / 0 / 0~1 的部分分")
    r.add_argument("--hints", type=int, default=0, help="用了提示的次数（>0 则不计入证据）")
    r.add_argument("--question", default="")
    r.add_argument("--note", default="")
    r.add_argument("--json", action="store_true")

    s = sub.add_parser("status", help="查看掌握状态")
    s.add_argument("--kp", default=None)
    s.add_argument("--json", action="store_true")
    ls = sub.add_parser("list", help="列出全部知识点状态")
    ls.add_argument("--kp", default=None)
    ls.add_argument("--json", action="store_true")

    q = sub.add_parser("qualify", help="标记概念/设计类定性通过")
    q.add_argument("--kp", required=True)
    q.add_argument("--note", default="")

    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "record":
        return cmd_record(args)
    if args.cmd in ("status", "list"):
        if not hasattr(args, "json"):
            args.json = False
        return cmd_status(args)
    if args.cmd == "qualify":
        return cmd_qualify(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
