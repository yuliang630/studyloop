#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记忆库维护工具（L1 痕迹 / L2 事实 / L3 综合）。

设计原则（全部有出处）：
  1. L1 只追加，永不修改 —— 证据链的底座；
  2. L2 每条事实必须带 L1 的 turn_id 作为证据，断链即视为不可信；
  3. recall 只输出"标签 + 时间 + days_ago"，不吐正文（避免把记忆内容灌进交互路径）；
  4. 固化（L1→L2）由模型判断、由本脚本保证格式，不在这里调模型。

用法：
  python mem.py init
  python mem.py stats
  python mem.py recall --days 7 --limit 20
  python mem.py digest --hours 24
  python mem.py fact-add --text "..." --evidence trn_xxx
  python mem.py fact-list
  python mem.py verify
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _console_probe() -> None:
    """诊断：被插件调起时，记录本进程有没有控制台窗口（0 = 没有）。"""
    if not os.environ.get("MEM_CONSOLE_PROBE"):
        return
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        handle = "na"
    try:
        path = os.path.join(os.environ.get("TEMP", "."), "study-console-probe.log")
        with open(path, "a", encoding="utf-8") as f:
            cmd = sys.argv[1] if len(sys.argv) > 1 else "?"
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{cmd}\t{handle}\n")
    except Exception:
        pass


_console_probe()

import paths as _paths
import profile_spec as _spec

ROOT = _paths.require_root()
DATA = os.path.join(ROOT, "data")
L1_DIR = os.path.join(DATA, "L1")
L2_DIR = os.path.join(DATA, "L2")
L3_DIR = os.path.join(DATA, "L3")
STATE_DIR = os.path.join(DATA, "state")
CONFIG = os.path.join(ROOT, "config.json")

DEFAULT_CONFIG = {
    "scope_note": "已废弃：scope 由 RECALLOOP_SCOPE 或 --scope 决定，本字段不再参与解析",
    "limits": {"summary_chars": 800, "inject_chars": 1500, "seen_cap": 100},
}


def load_config() -> dict:
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def scope_of(args) -> str:
    """scope 的唯一解析入口在 paths.resolve_scope，生产端与消费端共用。"""
    return _paths.resolve_scope(getattr(args, "scope", None))


def inject_chars(override=None) -> int:
    """整块注入预算：显式 --chars 优先，否则读 limits.inject_chars（不再是无读取方的死配置）。"""
    if override:
        return int(override)
    try:
        return int(load_config().get("limits", {}).get("inject_chars", 1500) or 1500)
    except Exception:
        return 1500


# ---------------------------------------------------------------- 目录


def ensure_tree(scope: str) -> None:
    for d in (L1_DIR, L2_DIR, L3_DIR, STATE_DIR, os.path.join(L3_DIR, scope)):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(CONFIG):
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- L1 读取


def l1_files() -> list[str]:
    if not os.path.isdir(L1_DIR):
        return []
    out = [os.path.join(L1_DIR, n) for n in sorted(os.listdir(L1_DIR)) if n.endswith(".jsonl")]
    return out


def read_l1(scope: str | None = None) -> list[dict]:
    rows: list[dict] = []
    for path in l1_files():
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if scope and rec.get("scope") != scope:
                        continue
                    rows.append(rec)
        except Exception as exc:  # 读不了就说读不了，不静默
            print(f"[warn] 读取失败 {path}: {exc}", file=sys.stderr)
    def _ts(r):
        t = parse_iso(r.get("ended_at") or r.get("started_at") or "")
        return t.timestamp() if t else 0.0

    rows.sort(key=_ts)
    return rows


def parse_iso(text: str) -> dt.datetime | None:
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text)
    except Exception:
        return None


def days_ago(value: str) -> str:
    ts = parse_iso(value)
    if not ts:
        return "?"
    now = dt.datetime.now(ts.tzinfo) if ts.tzinfo else dt.datetime.now()
    return str((now - ts).days)


# ---------------------------------------------------------------- 命令


def ensure_profile_skeleton(scope: str) -> bool:
    """T3：init 时落空骨架，区分"不存在"与"存在但未填充"。已存在则不动。"""
    target = os.path.join(L3_DIR, scope, "profile.md")
    if os.path.exists(target):
        return False
    text = _spec.MARK + "\n\n" + "\n\n".join(p + "\n" for p in _spec.PARAS)
    _atomic_write(target, text)
    return True


def cmd_init(args) -> int:
    scope = scope_of(args)
    ensure_tree(scope)
    created = ensure_profile_skeleton(scope)
    print("记忆库已就绪：")
    for label, path in (("根目录", ROOT), ("L1", L1_DIR), ("L2", L2_DIR), ("L3", L3_DIR), ("状态", STATE_DIR)):
        print(f"  {label:<8} {path}")
    print(f"  当前 scope: {scope}")
    print("  画像骨架：%s" % ("已创建（待填充）" if created else "已存在，未改动"))
    return 0


def cmd_stats(args) -> int:
    scope = scope_of(args)
    rows = read_l1(scope)
    per_day: dict[str, int] = {}
    for r in rows:
        day = (r.get("ended_at") or r.get("started_at") or "")[:10]
        per_day[day] = per_day.get(day, 0) + 1
    print(f"scope={scope}")
    print(f"L1 记录数: {len(rows)}")
    print(f"覆盖天数: {len(per_day)}")
    for day in sorted(per_day)[-10:]:
        print(f"  {day}  {per_day[day]} 条")
    l2_path = os.path.join(L2_DIR, f"{scope}.md")
    if os.path.exists(l2_path):
        facts = count_facts(scope)
        print(f"L2 事实数: {facts}")
    else:
        print("L2 事实数: 0（尚未固化）")
    return 0


def cmd_recall(args) -> int:
    """只输出标签与时间戳，不吐正文。"""
    scope = scope_of(args)
    rows = read_l1(scope)
    if not rows:
        print("（记忆库为空）")
        return 0
    cutoff = None
    if args.days:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    hits = []
    for r in rows:
        ts = parse_iso(r.get("ended_at") or r.get("started_at") or "")
        if cutoff and ts:
            ts_cmp = ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
            if ts_cmp < cutoff:
                continue
        hits.append(r)
    hits = hits[-args.limit:]
    for r in hits:
        _t = parse_iso(r.get("ended_at") or r.get("started_at") or "")
        when = _t.astimezone().strftime("%Y-%m-%d %H:%M") if _t else "?"
        _d = r.get("ended_at") or r.get("started_at") or ""
        label = (r.get("excerpt") or r.get("summary") or "").replace("\n", " ")[:40]
        print(f"[{when}] d-{days_ago(_d)} "
              f"{r.get('turn_id')} {label}...")
    print(f"（共 {len(hits)} 条，scope={scope}）")
    return 0


def cmd_digest(args) -> int:
    """固化用：输出近期完整摘要，供模型判断哪些值得进 L2。"""
    scope = scope_of(args)
    rows = read_l1(scope)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.hours)
    picked = []
    for r in rows:
        ts = parse_iso(r.get("ended_at") or r.get("started_at") or "")
        if not ts:
            continue
        ts_cmp = ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
        if ts_cmp >= cutoff:
            picked.append(r)
    if not picked:
        print(f"近 {args.hours} 小时无新记录")
        return 0
    for r in picked:
        print(f"### {r.get('turn_id')}  {r.get('ended_at')}")
        print(r.get("excerpt") or r.get("summary") or "（无摘录）")
        print()
    print(f"（近 {args.hours} 小时 {len(picked)} 条，待判断是否固化）")
    return 0


FACT_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · (.+?) <!--\s*ev:\s*([^>]*)-->$")


def l2_path(scope: str) -> str:
    return os.path.join(L2_DIR, f"{scope}.md")


def count_facts(scope: str) -> int:
    path = l2_path(scope)
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if FACT_RE.match(line.rstrip("\n")):
                n += 1
    return n


def cmd_fact_add(args) -> int:
    scope = scope_of(args)
    ensure_tree(scope)
    evidence = [e.strip() for e in re.split(r"[,\s]+", args.evidence) if e.strip()]
    if not evidence:
        print("[error] 必须提供 --evidence（L1 的 turn_id）", file=sys.stderr)
        return 2
    known = {r.get("turn_id") for r in read_l1(scope)}
    missing = [e for e in evidence if e not in known]
    if missing:
        print(f"[error] 证据不存在: {', '.join(missing)}", file=sys.stderr)
        return 2
    text = " ".join(args.text.split())
    day = dt.date.today().isoformat()
    path = l2_path(scope)
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new_file:
            f.write(f"# L2 事实 · scope={scope}\n\n")
        f.write(f"- {day} · {text} <!-- ev: {','.join(evidence)} -->\n")
    print(f"已写入 L2：{text[:60]}")
    return 0


def cmd_fact_list(args) -> int:
    scope = scope_of(args)
    path = l2_path(scope)
    if not os.path.exists(path):
        print("（L2 为空）")
        return 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if FACT_RE.match(line.rstrip("\n")):
                print(line.rstrip("\n"))
    return 0


def cmd_verify(args) -> int:
    """断链校验：每条 L2 事实的证据都必须能在 L1 找到。"""
    scope = scope_of(args)
    path = l2_path(scope)
    if not os.path.exists(path):
        print("（L2 为空，无需校验）")
        return 0
    known = {r.get("turn_id") for r in read_l1(scope)}
    total = broken = 0
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = FACT_RE.match(line.rstrip("\n"))
            if not m:
                continue
            total += 1
            evs = [e.strip() for e in m.group(3).split(",") if e.strip()]
            missing = [e for e in evs if e not in known]
            if missing:
                broken += 1
                print(f"[断链] 第 {lineno} 行 证据缺失: {', '.join(missing)}")
    print(f"校验完成：{total} 条事实，断链 {broken} 条")
    return 1 if broken else 0


def cmd_forget(args) -> int:
    """按会话或轮次删除 L1 记录（先归档，再删除，不静默丢数据）。"""
    if not args.sid and not args.turn:
        print("[error] 必须指定 --sid 或 --turn", file=sys.stderr)
        return 2
    scope = scope_of(args)
    removed: list[dict] = []
    touched = 0
    for path in l1_files():
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        keep: list[str] = []
        changed = False
        for line in lines:
            text = line.strip()
            if not text:
                keep.append(line)
                continue
            try:
                rec = json.loads(text)
            except Exception:
                keep.append(line)
                continue
            hit = (args.sid and rec.get("sid") == args.sid) or (
                args.turn and rec.get("turn_id") == args.turn
            )
            if hit:
                removed.append(rec)
                changed = True
            else:
                keep.append(line)
        if changed:
            touched += 1
            if not args.dry_run:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(keep)
                os.replace(tmp, path)
    if not removed:
        print("未匹配到任何记录")
        return 0
    if args.dry_run:
        print(f"[dry-run] 将删除 {len(removed)} 条，涉及 {touched} 个文件")
    else:
        ensure_tree(scope)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        arc = os.path.join(STATE_DIR, f"forget-archive-{stamp}.jsonl")
        with open(arc, "w", encoding="utf-8") as f:
            for r in removed:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"已删除 {len(removed)} 条，涉及 {touched} 个文件")
        print(f"已归档到 {arc}")
    for r in removed[:10]:
        print(f"  {r.get('turn_id')}  {(r.get('excerpt') or '')[:40]}")
    return 0


# ---------------------------------------------------------------- 跨 agent 接口


KEEP_TYPES = {"user", "assistant"}
TEXT_PART_TYPES = {"text", "output_text", ""}
FRESH_SECONDS = 600  # 只处理 10 分钟内仍有活动的会话，防回填


def parse_msg_time(value):
    """消息 time 可能是字符串/数字/对象（OpenCode 用 {created,firstToken,...}）。

    注意单位：真实 payload 里是**毫秒整数**（13 位），而 Python 的
    fromtimestamp 只接受**秒**。不做换算会抛 OSError: [Errno 22]。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e11:  # 秒级时间戳在 5138 年前不会超过 1e11，超过即视为毫秒
            v /= 1000.0
        try:
            return dt.datetime.fromtimestamp(v, dt.timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str) and value:
        try:
            ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
        except Exception:
            return None
    if isinstance(value, dict):
        for key in ("created", "completed", "start", "end", "timestamp", "ms", "value"):
            if key in value:
                hit = parse_msg_time(value[key])
                if hit:
                    return hit
    return None


def extract_text(value) -> str:
    """只取正文分片，跳过 reasoning / tool 分片。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out = []
        for part in value:
            if isinstance(part, str):
                out.append(part)
                continue
            if isinstance(part, dict):
                kind = str(part.get("type", ""))
                if kind not in TEXT_PART_TYPES:
                    continue
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    out.append(text)
        return "\n".join(x for x in out if x)
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    return ""


def cursor_path() -> str:
    return os.path.join(STATE_DIR, "cursors.json")


def load_cursors() -> dict:
    try:
        with open(cursor_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cursors(data: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = cursor_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8", errors="replace") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, cursor_path())


def build_progress_block(root: str) -> str:
    """学习进度与今日复习，直接读 state 文件（不 import 其它模块，保持轻）。"""
    st_dir = os.path.join(root, "data", "state")
    lines: list[str] = []

    # 路径：下一条未完成的课
    try:
        with open(os.path.join(st_dir, "path.json"), "r", encoding="utf-8") as f:
            path_data = json.load(f)
        items = path_data.get("items") or []
        todo = next((x for x in items if not x.get("done")), None)
        done = sum(1 for x in items if x.get("done"))
        if items:
            if todo:
                lines.append(f"- 进度：{done}/{len(items)} 已完成，下一课 **{todo['id']} {todo['title']}**")
            else:
                lines.append(f"- 进度：{done}/{len(items)}，全部完成")
    except Exception:
        pass

    # 复习：今日到期数量
    try:
        with open(os.path.join(st_dir, "reviews.json"), "r", encoding="utf-8") as f:
            reviews = json.load(f)
        now = dt.datetime.now().timestamp()
        due = [k for k, v in reviews.items() if float(v.get("due_at", 0)) <= now]
        if reviews:
            if due:
                head = "、".join(due[:3]) + ("…" if len(due) > 3 else "")
                lines.append(f"- 今日待复习：**{len(due)}** 条（{head}）——先复习再学新的")
            else:
                lines.append("- 今日待复习：0 条")
    except Exception:
        pass

    if not lines:
        return ""
    return "## 学习进度\n" + "\n".join(lines)


# ---------------------------------------------------------------- L3 画像

PROFILE_MARK = _spec.MARK
PROFILE_LIMITS = {"profile": _spec.LIMITS["profile"], "recent": _spec.LIMITS["recent"]}
NAME_MAX = _spec.NAME_MAX
ID_MAX = _spec.ID_MAX
PROFILE_COUNTS = _spec.COUNTS
RECENT_MAX_ITEMS = _spec.RECENT_MAX_ITEMS
RECENT_DAYS = _spec.RECENT_DAYS
RHYTHM_DAYS = _spec.RHYTHM_DAYS


def _clip(text, limit: int) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"


def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    rows.append(rec)
    except Exception as exc:
        print(f"[warn] 读取失败 {path}: {exc}", file=sys.stderr)
    return rows


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _has_generated_mark(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.readline().strip() == PROFILE_MARK
    except Exception:
        return False


def _attempt_index() -> dict[str, list[dict]]:
    by_kp: dict[str, list[dict]] = {}
    for row in _read_jsonl(os.path.join(STATE_DIR, "attempts.jsonl")):
        kp = row.get("kp")
        if not kp:
            continue
        by_kp.setdefault(str(kp), []).append(row)
    for items in by_kp.values():
        items.sort(key=lambda r: str(r.get("ts") or ""))
    return by_kp


def _mastery_rows(by_kp: dict[str, list[dict]]) -> list[dict]:
    import mastery as _mastery  # 同目录，无副作用
    out = []
    for kp, items in by_kp.items():
        evidence = [float(r.get("correct", 0)) for r in items
                    if int(r.get("hints", 0) or 0) == 0]
        kp_type = str(items[-1].get("type") or "memory")
        m = _mastery.compute_mastery(evidence)
        out.append({
            "kp": kp,
            "type": kp_type,
            "mastery": round(m, 3),
            "threshold": round(_mastery.gate_threshold(kp_type), 2),
            "passed": bool(_mastery.is_mastered(kp_type, m)),
        })
    out.sort(key=lambda x: (x["passed"], x["mastery"], x["kp"]))
    return out[:PROFILE_COUNTS["mastery"]]


def _weak_rows(by_kp: dict[str, list[dict]]) -> list[dict]:
    out = []
    for kp, items in by_kp.items():
        last = items[-1]
        correct = float(last.get("correct", 0))
        hints = int(last.get("hints", 0) or 0)
        if correct < 1 or hints > 0:
            out.append({"kp": kp, "correct": correct, "hints": hints,
                        "ts": str(last.get("ts") or "")})
    out.sort(key=lambda x: (x["ts"], x["kp"]), reverse=True)
    return out[:PROFILE_COUNTS["weak"]]


def _goal_rows() -> list[dict]:
    data = _load_json(os.path.join(STATE_DIR, "path.json"), {})
    items = data.get("items") or []
    ordered = [x for x in items if not x.get("done")] + [x for x in items if x.get("done")]
    return ordered[:PROFILE_COUNTS["goal"]]


def _within(rec: dict, now: dt.datetime, days: int) -> bool:
    ts = parse_iso(str(rec.get("ended_at") or rec.get("started_at") or ""))
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.astimezone()
    return (now - ts).days < days


def _trim_profile(text: str, limit: int = PROFILE_LIMITS["profile"]) -> str:
    """按段落优先级裁剪，实现统一在 profile_spec.trim。"""
    return _spec.trim(text, limit)


def build_profile_text(scope: str) -> str:
    """按 PLAN-L3-schema 的四段结构生成 profile.md。"""
    by_kp = _attempt_index()
    lines = [PROFILE_MARK, "", "### 目标与进度"]
    goals = _goal_rows()
    if goals:
        for x in goals:
            lines.append(_spec.GOAL_LINE.format(
                id=_clip(x.get("id", ""), ID_MAX),
                title=_clip(x.get("title", ""), NAME_MAX),
                status="已完成" if x.get("done") else "未完成"))
    else:
        lines.append(_spec.EMPTY_ITEMS[_spec.PARAS[0]])

    lines += ["", "### 掌握度概览"]
    mastery = _mastery_rows(by_kp)
    if mastery:
        for r in mastery:
            lines.append(_spec.MASTERY_LINE.format(
                kp=_clip(r["kp"], NAME_MAX), mastery=r["mastery"],
                threshold=r["threshold"], status="达标" if r["passed"] else "未达标"))
    else:
        lines.append(_spec.EMPTY_ITEMS[_spec.PARAS[1]])

    lines += ["", "### 薄弱环节"]
    weak = _weak_rows(by_kp)
    if weak:
        for r in weak:
            lines.append(_spec.WEAK_LINE.format(
                kp=_clip(r["kp"], NAME_MAX), correct=r["correct"], hints=r["hints"]))
    else:
        lines.append(_spec.EMPTY_ITEMS[_spec.PARAS[2]])

    now = dt.datetime.now().astimezone()
    rows = read_l1(scope)
    active = {parse_iso(str(r.get("ended_at") or r.get("started_at") or "")).date()
              for r in rows
              if _within(r, now, RHYTHM_DAYS)
              and parse_iso(str(r.get("ended_at") or r.get("started_at") or "")) is not None}
    count = len([r for r in rows if _within(r, now, RHYTHM_DAYS)])
    lines += ["", "### 学习节奏",
              _spec.RHYTHM_LINE.format(days=RHYTHM_DAYS, active=len(active), count=count), ""]
    return _trim_profile("\n".join(lines))


def build_recent_text(scope: str) -> str:
    now = dt.datetime.now().astimezone()
    rows = [r for r in read_l1(scope) if _within(r, now, RECENT_DAYS)]
    rows = rows[-RECENT_MAX_ITEMS:]
    lines = [PROFILE_MARK]
    for r in rows:
        ts = parse_iso(str(r.get("ended_at") or r.get("started_at") or ""))
        day = ts.astimezone().strftime("%Y-%m-%d") if ts else "????-??-??"
        lines.append("- %s %s" % (day, _clip(r.get("excerpt") or r.get("summary") or "", 60)))
    if not rows:
        lines.append("- 近期暂无记录。")
    text = "\n".join(lines) + "\n"
    while len(text) > PROFILE_LIMITS["recent"] and len(lines) > 2:
        lines.pop(1)
        text = "\n".join(lines) + "\n"
    return text


def cmd_profile(args) -> int:
    """T1：生成画像与近期动态；T2：--check 严格校验。"""
    scope = scope_of(args)
    ensure_tree(scope)

    if getattr(args, "check", False):
        target = os.path.join(L3_DIR, scope, "profile.md")
        text = None
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8-sig") as f:
                text = f.read()
        key, detail = _spec.validate(text)
        print(f"{_spec.TOKENS[key]} {detail}")
        return _spec.EXIT_CODES[key]

    if not getattr(args, "build", False):
        print("[error] 需要 --build 或 --check", file=sys.stderr)
        return 2

    target = os.path.join(L3_DIR, scope, "profile.md")
    if os.path.exists(target) and not _has_generated_mark(target):
        if not getattr(args, "force", False):
            print("[error] 已存在无生成标记的 profile.md，拒写；确认后加 --force",
                  file=sys.stderr)
            return 1
        backup = target + ".bak-" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
        try:
            shutil.copy2(target, backup)
        except Exception as exc:
            print(f"[error] 备份失败，已中止：{exc}", file=sys.stderr)
            return 1
        print(f"[ok] 已备份原文件至 {backup}")

    profile = build_profile_text(scope)
    recent = build_recent_text(scope)
    _atomic_write(target, profile)
    _atomic_write(os.path.join(L3_DIR, scope, "recent.md"), recent)
    print(f"[ok] 画像已生成（{len(profile)} 字符）：{target}")
    print(f"[ok] 近期动态已生成（{len(recent)} 字符）")
    return 0


def build_inject_block(scope: str, chars: int) -> str:
    """拼出可注入的记忆块（不含通道状态）。"""
    profile_path = os.path.join(L3_DIR, scope, "profile.md")
    recent_path = os.path.join(L3_DIR, scope, "recent.md")
    profile = ""
    recent = ""
    for path, target in ((profile_path, "profile"), (recent_path, "recent")):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                if target == "profile":
                    profile = _trim_profile(f.read())
                else:
                    recent = f.read()
    progress = build_progress_block(ROOT)
    if not profile.strip() and not recent.strip() and not progress:
        return "（记忆库尚未建立）"
    return _spec.render(profile, recent, progress, chars)


def cmd_inject(args) -> int:
    """输出可被注入 system 的记忆块（stdout）。任何能调命令的 agent 都能用。"""
    block = build_inject_block(scope_of(args), inject_chars(getattr(args, "chars", None)))
    if args.out:
        target = args.out
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(block + "\n")
        os.replace(tmp, target)
        return 0
    print(block)
    return 0


def cmd_ingest(args) -> int:
    """从 stdin 或文件读一份消息数组，追加本轮到 L1。核心逻辑与插件一致。"""
    try:
        return _ingest(args)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(os.path.join(STATE_DIR, "last-ingest-error.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        return 3


def _ingest(args) -> int:
    scope = scope_of(args)
    ensure_tree(scope)
    try:
        if args.from_stdin:
            raw = sys.stdin.read()
        else:
            with open(args.file, "r", encoding="utf-8") as f:
                raw = f.read()
        data = json.loads(raw)
    except Exception as exc:
        print(f"[error] 读取消息失败: {exc}", file=sys.stderr)
        return 2
    items = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        print("[error] 消息为空或格式不对", file=sys.stderr)
        return 2
    # 真实 payload 可能混入 null 或非对象元素，先净化，避免 .get 崩掉整轮
    raw_count = len(items)
    items = [m for m in items if isinstance(m, dict)]
    if len(items) != raw_count:
        print(f"[warn] 丢弃 {raw_count - len(items)} 个非对象元素", file=sys.stderr)

    sid = args.sid or next((str(m.get("sessionID")) for m in items if m.get("sessionID")), "unknown")

    last_ts = None
    for m in reversed(items):
        last_ts = parse_msg_time(m.get("time"))
        if last_ts:
            break
    now = dt.datetime.now(dt.timezone.utc)
    if last_ts and (now - last_ts).total_seconds() > FRESH_SECONDS:
        print(f"[skip] 会话陈旧（{(now - last_ts).total_seconds() / 60:.0f} 分钟无活动），不回填")
        return 0

    cursors = load_cursors()
    cur = cursors.get(sid, {})
    seen = set(cur.get("seen", []))
    if args.all:
        start = 0
    elif cur.get("last_id"):
        idx = next((i for i, m in enumerate(items) if m.get("id") == cur["last_id"]), -1)
        start = idx + 1 if idx >= 0 else max(0, len(items) - 8)
        if idx < 0:
            print("[warn] 游标失配，降级取最近 8 条", file=sys.stderr)
    else:
        start = max(0, len(items) - 8)

    def slice_from(pos: int):
        return [
            m for m in items[pos:]
            if str(m.get("type", "")) in KEEP_TYPES and m.get("id") and m.get("id") not in seen
        ]

    fresh = slice_from(start)
    # 关键修正：一轮长课会产生连续多条 assistant，"取最近 N 条"里可能一个 user 都没有。
    # 这时必须回退到最后一条 user，否则整轮被误判为"无内容"并推进游标。
    if not any(str(m.get("type")) == "user" for m in fresh):
        last_user = max((i for i, m in enumerate(items) if str(m.get("type")) == "user"), default=-1)
        if last_user >= 0 and last_user < start:
            print(f"[warn] 窗口内无 user，回退至最后一条 user（index={last_user}）", file=sys.stderr)
            start = last_user
            fresh = slice_from(start)

    while fresh and str(fresh[0].get("type")) != "user":
        fresh.pop(0)

    if not fresh:
        last_id = str(items[-1].get("id") or "")
        if last_id:
            cursors[sid] = {"last_id": last_id, "seen": list(seen)[-100:]}
            save_cursors(cursors)
        print("[skip] 无新增对话内容")
        return 0

    lines = []
    for m in fresh:
        who = str(m.get("type"))
        body = extract_text(m.get("text")) if who == "user" else extract_text(m.get("content"))
        if body.strip():
            lines.append(f"[{who}] {body.strip()}")
    if not lines:
        print("[skip] 过滤后无正文")
        return 0

    excerpt = "\n".join(lines)
    if len(excerpt) > 800:
        excerpt = excerpt[:800] + "…[截断]"

    start_ts = parse_msg_time(fresh[0].get("time")) or now
    end_ts = parse_msg_time(fresh[-1].get("time")) or now
    rec = {
        "v": 1,
        "turn_id": "trn_" + now.strftime("%Y%m%d_") + os.urandom(4).hex(),
        "scope": scope,
        "sid": sid,
        "surface": args.surface,
        "started_at": start_ts.astimezone().isoformat(),
        "ended_at": end_ts.astimezone().isoformat(),
        "msg_ids": [str(m.get("id")) for m in fresh],
        "msg_count": len(fresh),
        "excerpt": excerpt,
    }
    path = os.path.join(L1_DIR, end_ts.astimezone().strftime("%Y-%m-%d") + ".jsonl")
    with open(path, "a", encoding="utf-8", errors="replace") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for m in fresh:
        seen.add(str(m.get("id")))
    cursors[sid] = {"last_id": str(fresh[-1].get("id")), "seen": list(seen)[-100:]}
    save_cursors(cursors)
    print(f"[ok] 写入 L1 {rec['turn_id']} msgs={len(fresh)} chars={len(excerpt)}")

    # 顺手刷新注入缓存：每轮只起一个 Python 进程，少一次窗口机会
    out_path = getattr(args, "refresh_out", None)
    if out_path:
        try:
            cmd_inject(argparse.Namespace(scope=scope, chars=None, out=out_path))
        except Exception as exc:
            print(f"[warn] 刷新注入缓存失败: {exc}", file=sys.stderr)
    return 0


def hook_heartbeat() -> dict:
    path = os.path.join(STATE_DIR, "hook.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def channel_status(transport: str = "") -> tuple[str, str]:
    """返回 (通道说明, 本轮动作)。有钩子、有 MCP、都没有，各自该干什么。"""
    if transport == "mcp":
        return "MCP（本次调用来自 MCP 服务端）", "开课已注入；本轮结束调 recalloop_note"
    hb = hook_heartbeat()
    ts = parse_iso(hb.get("last_ingest_at", ""))
    if ts:
        now = dt.datetime.now(ts.tzinfo) if ts.tzinfo else dt.datetime.now()
        minutes = int((now - ts).total_seconds() // 60)
        turns = hb.get("turns", "?")
        if minutes <= 60:
            return (f"钩子 工作中（{minutes} 分钟前，已记 {turns} 轮）",
                    "本轮结束不需要手动记账")
        days = minutes // 1440
        age = f"{days} 天前" if days else f"{minutes // 60} 小时前"
        return (f"钩子 未工作（最后写入 {age}）",
                '本轮结束请跑 mem.py note --text "<一句话总结>"')
    return ("未检测到钩子", '本轮结束请跑 mem.py note --text "<一句话总结>"')


def cmd_boot(args) -> int:
    """一条命令完成开课注入：记忆块 + 通道状态 + 本轮该做什么。"""
    scope = scope_of(args)
    ensure_tree(scope)
    block = build_inject_block(scope, inject_chars(getattr(args, "chars", None)))
    status, action = channel_status(getattr(args, "transport", "") or "")

    if args.out:
        target = args.out
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(block + "\n")
        os.replace(tmp, target)
        print(f"[ok] 注入缓存已写入 {os.path.relpath(target, ROOT) if target.startswith(ROOT) else target}")
        print(f"     通道：{status}")
        print(f"     本轮动作：{action}")
        return 0

    print(block)
    print()
    print("== 记忆通道 ==")
    print(f"通道        {status}")
    print(f"本轮动作    {action}")
    return 0


def _turn_key(sid: str, text: str) -> str:
    import hashlib
    return hashlib.sha256((sid + "\n" + text).encode("utf-8")).hexdigest()[:16]


def cmd_note(args) -> int:
    """无钩子宿主的记账通道：写一条 L1，来源标 agent-note，按内容去重。"""
    scope = scope_of(args)
    ensure_tree(scope)
    text = (args.text or "").strip()
    if not text:
        print("[error] --text 不能为空", file=sys.stderr)
        return 2

    sid = (args.sid or os.environ.get("RECALLOOP_SID")
               or os.environ.get("STUDYLOOP_SID") or "agent")
    key = _turn_key(sid, text)
    if not args.force:
        for rec in read_l1(scope):
            if rec.get("turn_key") == key:
                print(f"[skip] 该轮已记账（{rec.get('turn_id')}），不重复写入")
                return 0

    now = dt.datetime.now(dt.timezone.utc)
    rec = {
        "v": 1,
        "turn_id": "trn_" + now.strftime("%Y%m%d_") + os.urandom(4).hex(),
        "turn_key": key,
        "scope": scope,
        "sid": sid,
        "surface": args.surface or "agent-note",
        "source": "agent-note",
        "started_at": now.astimezone().isoformat(),
        "ended_at": now.astimezone().isoformat(),
        "msg_ids": [],
        "msg_count": 0,
        "excerpt": text[:800],
    }
    path = os.path.join(L1_DIR, now.astimezone().strftime("%Y-%m-%d") + ".jsonl")
    with open(path, "a", encoding="utf-8", errors="replace") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[ok] 已记账 {rec['turn_id']}（来源 agent-note，sid={sid}）")

    out_path = getattr(args, "refresh_out", None)
    if out_path:
        try:
            cmd_inject(argparse.Namespace(scope=scope, chars=None, out=out_path))
        except Exception as exc:
            print(f"[warn] 刷新注入缓存失败: {exc}", file=sys.stderr)
    return 0


def _read_attempt_times() -> list[dt.datetime]:
    path = os.path.join(STATE_DIR, "attempts.jsonl")
    out: list[dt.datetime] = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                t = parse_iso(str(rec.get("ts", "")))
                if t:
                    out.append(t)
    except Exception:
        pass
    return out


def cmd_audit(args) -> int:
    """对账：哪些天做了题却没有对话记录，哪些轮次只是 agent 自述。"""
    days = args.days
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=days)

    rows = [r for r in read_l1() if (parse_iso(r.get("ended_at") or "") or cutoff) >= cutoff]
    by_day: dict[str, dict[str, int]] = {}
    for r in rows:
        t = parse_iso(r.get("ended_at") or "")
        if not t:
            continue
        day = t.astimezone().strftime("%Y-%m-%d")
        slot = by_day.setdefault(day, {"ingest": 0, "note": 0})
        if r.get("source") == "agent-note":
            slot["note"] += 1
        else:
            slot["ingest"] += 1

    att_by_day: dict[str, int] = {}
    for t in _read_attempt_times():
        if t >= cutoff:
            att_by_day[t.astimezone().strftime("%Y-%m-%d")] = \
                att_by_day.get(t.astimezone().strftime("%Y-%m-%d"), 0) + 1

    all_days = sorted(set(by_day) | set(att_by_day))
    gaps = [d for d in all_days if att_by_day.get(d, 0) > 0 and not by_day.get(d)]

    sids: dict[str, dict] = {}
    for r in rows:
        sid = str(r.get("sid") or "?")
        slot = sids.setdefault(sid, {"turns": 0, "notes": 0, "last": ""})
        slot["turns"] += 1
        if r.get("source") == "agent-note":
            slot["notes"] += 1
        ts = str(r.get("ended_at") or "")
        if ts > slot["last"]:
            slot["last"] = ts

    if args.json:
        print(json.dumps({
            "days": days,
            "days_table": all_days,
            "by_day": by_day,
            "attempts_by_day": att_by_day,
            "gaps": gaps,
            "sessions": sids,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"== 对账（最近 {days} 天）==")
    if not all_days:
        print("  没有记录。")
        return 0
    print(f"{'日期':<12}{'原始记录':>8}{'agent 自述':>10}{'作答':>6}  备注")
    for d in all_days:
        slot = by_day.get(d, {"ingest": 0, "note": 0})
        att = att_by_day.get(d, 0)
        note = ""
        if att and not (slot["ingest"] + slot["note"]):
            note = "有作答但没有对话记录 ← 缺账"
        elif slot["note"] and not slot["ingest"]:
            note = "只有自述记录"
        print(f"{d:<12}{slot['ingest']:>8}{slot['note']:>10}{att:>6}  {note}")

    if gaps:
        print()
        print(f"缺账 {len(gaps)} 天：{', '.join(gaps)}")
        print("  补法：把该天的对话文件跑一次 `mem.py ingest --file <文件>`；拿不到就 `mem.py note --text …`")
    else:
        print()
        print("没有发现缺账。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mem.py", description="记忆库维护工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (
        ("init", cmd_init),
        ("stats", cmd_stats),
        ("recall", cmd_recall),
        ("digest", cmd_digest),
        ("fact-add", cmd_fact_add),
        ("fact-list", cmd_fact_list),
        ("verify", cmd_verify),
        ("forget", cmd_forget),
        ("inject", cmd_inject),
        ("ingest", cmd_ingest),
        ("boot", cmd_boot),
        ("note", cmd_note),
        ("audit", cmd_audit),
        ("profile", cmd_profile),
    ):
        sp = sub.add_parser(name)
        sp.add_argument("--scope", default=None)
        if name == "boot":
            sp.add_argument("--chars", type=int, default=None)
            sp.add_argument("--out", default=None, help="把注入缓存写到这里（agent 直接读文件）")
            sp.add_argument("--transport", default=None, help="mcp / 留空自动判断")
        if name == "note":
            sp.add_argument("--text", required=True)
            sp.add_argument("--sid", default=None)
            sp.add_argument("--surface", default="agent-note")
            sp.add_argument("--force", action="store_true", help="忽略去重，强制写入")
            sp.add_argument("--refresh-out", default=None, help="写入后顺带刷新注入缓存")
        if name == "audit":
            sp.add_argument("--days", type=int, default=7)
            sp.add_argument("--json", action="store_true")
        if name == "forget":
            sp.add_argument("--sid", default=None)
            sp.add_argument("--turn", default=None)
            sp.add_argument("--dry-run", action="store_true")
        if name == "inject":
            sp.add_argument("--chars", type=int, default=None)
            sp.add_argument("--out", default=None)
        if name == "ingest":
            sp.add_argument("--from-stdin", action="store_true")
            sp.add_argument("--file", default=None)
            sp.add_argument("--sid", default=None)
            sp.add_argument("--surface", default="chat")
            sp.add_argument("--all", action="store_true", help="忽略游标，从头处理（用于补录）")
            sp.add_argument("--refresh-out", default=None, help="写入后顺带刷新注入缓存到该路径")
        if name == "recall":
            sp.add_argument("--days", type=int, default=7)
            sp.add_argument("--limit", type=int, default=20)
        if name == "digest":
            sp.add_argument("--hours", type=int, default=24)
        if name == "fact-add":
            sp.add_argument("--text", required=True)
            sp.add_argument("--evidence", required=True)
        if name == "profile":
            sp.add_argument("--build", action="store_true", help="生成 profile.md 与 recent.md")
            sp.add_argument("--check", action="store_true", help="严格校验画像结构（0/1/3）")
            sp.add_argument("--force", action="store_true", help="覆盖无生成标记的既有文件（先备份）")
        sp.set_defaults(func=fn)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
