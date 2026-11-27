#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成输入装配：把"素材 + 掌握度 + 错题 + 进度"拼成一份 brief，供 agent 生成产物。

只装配，不生成正文。

用法（在课程目录下）：
    python brief.py exam --topic "第01课" [--top 6] [--stdout]
    python brief.py lesson|handout|curriculum --topic "..." [--top 6]

输出：记录/brief-<类型>-<slug>.md（或 --stdout）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KIND_TITLES = {
    "exam": "试卷",
    "lesson": "教案",
    "handout": "讲义",
    "curriculum": "课程规划",
}

# 每类产物在模板里的必填段（与 templates/*.md 对应）
REQUIRED_SECTIONS = {
    "exam": ["命题蓝图", "题目", "答案与评分点", "来源"],
    "lesson": ["目标", "难点", "例子", "验收题", "预计时长", "前置", "来源"],
    "handout": ["术语表", "大纲", "参考"],
    "curriculum": ["目标", "起点", "知识点表", "依赖检查", "排期", "来源"],
}


def course_root() -> str:
    root = os.getcwd()
    if not os.path.exists(os.path.join(root, ".study-workspace")):
        raise SystemExit("[error] 当前目录不是课程工作区（缺 .study-workspace）")
    return root


def course_name(root: str) -> str:
    try:
        with open(os.path.join(root, ".study-workspace"), "r", encoding="utf-8-sig") as f:
            return str(json.load(f).get("name") or os.path.basename(root))
    except Exception:
        return os.path.basename(root)


def state_path(root: str, name: str) -> str:
    return os.path.join(root, "记忆", "data", "state", name)


def read_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def mastery_summary(root: str) -> list[dict]:
    import mastery  # noqa: E402

    rows = read_jsonl(state_path(root, "attempts.jsonl"))
    by_kp: dict[str, dict] = {}
    for r in rows:
        kp = r.get("kp")
        if not kp:
            continue
        item = by_kp.setdefault(kp, {"kp": kp, "type": r.get("type", "memory"), "evidence": [], "total": 0, "hints": 0})
        item["total"] += 1
        if int(r.get("hints", 0) or 0) == 0:
            item["evidence"].append(float(r.get("correct", 0)))
        else:
            item["hints"] += 1
    out = []
    for item in by_kp.values():
        m = mastery.compute_mastery(item["evidence"])
        out.append({
            "kp": item["kp"], "type": item["type"], "mastery": round(m, 3),
            "threshold": mastery.gate_threshold(item["type"]),
            "passed": bool(mastery.is_mastered(item["type"], m)),
            "attempts": item["total"], "hints": item["hints"],
        })
    out.sort(key=lambda x: (x["passed"], x["mastery"]))
    return out


def error_records(root: str, limit: int = 8) -> list[dict]:
    rows = read_jsonl(state_path(root, "attempts.jsonl"))
    bad = [r for r in rows if float(r.get("correct", 0)) < 1.0]
    bad.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return bad[:limit]


def path_position(root: str) -> dict:
    data = read_json(state_path(root, "path.json"), {})
    items = data.get("items") or []
    if not items:
        return {}
    done = [x for x in items if x.get("done")]
    todo = next((x for x in items if not x.get("done")), None)
    return {"total": len(items), "done": len(done), "next": todo, "source": data.get("source", "")}


def due_reviews(root: str) -> list[str]:
    data = read_json(state_path(root, "reviews.json"), {})
    now = dt.datetime.now().timestamp()
    return [k for k, v in data.items() if float(v.get("due_at", 0)) <= now]


def material_hits(root: str, query: str, top: int) -> tuple[list[dict], str]:
    """用现有索引检索素材；索引不存在则提示。"""
    try:
        import retrieve as _r  # noqa: E402
    except Exception as exc:
        return [], f"检索模块不可用：{exc}"
    idx = _r.load_index()
    if not idx.get("chunks"):
        return [], "索引为空，先运行：python retrieve.py index"
    return _r.search(idx, query, top), ""


def build_brief(kind: str, topic: str, root: str, top: int) -> str:
    now = dt.date.today().isoformat()
    hits, note = material_hits(root, topic, top)
    master = mastery_summary(root)
    errors = error_records(root)
    pos = path_position(root)
    due = due_reviews(root)

    lines: list[str] = []
    lines.append(f"# 生成简报 · {KIND_TITLES[kind]}：{topic}")
    lines.append("")
    lines.append(f"> 课程：{course_name(root)} · 日期：{now} · 由 brief.py 自动生成")
    lines.append(f"> 目标产物类型：**{kind}**")
    lines.append("")
    lines.append("## 一、模板要求（必须包含这些段）")
    for sec in REQUIRED_SECTIONS.get(kind, []):
        lines.append(f"- {sec}")
    lines.append("")

    lines.append("## 二、素材片段（回答必须引用）")
    if hits:
        for i, h in enumerate(hits, 1):
            snippet = h.get("text", "").replace("\n", " ")[:300]
            lines.append(f"{i}. **{h.get('path')}**（score={h.get('score')}）")
            lines.append(f"   {snippet}")
    else:
        lines.append(f"- 无命中。{note or '换个关键词试试，或先建索引。'}")
    lines.append("")

    lines.append("## 三、学习者状态（决定难度与侧重）")
    if master:
        for m in master[:12]:
            flag = "已过" if m["passed"] else "未过"
            lines.append(f"- {m['kp']}（{m['type']}）：掌握度 {m['mastery']} / 门槛 {m['threshold']} · {flag}"
                         f" · 作答 {m['attempts']}" + (f" · 提示 {m['hints']}" if m["hints"] else ""))
    else:
        lines.append("- 尚无作答记录（全部按初学处理）")
    lines.append("")

    lines.append("## 四、近期错题（优先覆盖）")
    if errors:
        for e in errors:
            lines.append(f"- {e.get('ts', '')} · {e.get('kp')} · 得分 {e.get('correct')}"
                         + (f" · 提示 {e.get('hints')}" if int(e.get("hints", 0) or 0) else ""))
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 五、进度")
    if pos:
        lines.append(f"- 路径：{pos['done']}/{pos['total']} 已完成")
        nxt = pos.get("next")
        lines.append(f"- 下一课：{nxt['id']} {nxt['title']}" if nxt else "- 下一课：全部完成")
    else:
        lines.append("- 尚未建立路径（path.py init）")
    lines.append(f"- 今日到期复习：{len(due)} 条" + (f"（{', '.join(due[:3])}…）" if len(due) > 3 else ""))
    lines.append("")

    lines.append("## 六、交付要求")
    lines.append("- 按上面的模板段落逐段填写，不要增减段名")
    lines.append("- 每条事实性内容标注来源（素材路径）")
    lines.append("- 写完后运行：`python artifacts.py list` 与后续的 check 校验")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(prog="brief.py", description="生成输入装配")
    p.add_argument("kind", choices=sorted(KIND_TITLES))
    p.add_argument("--topic", required=True)
    p.add_argument("--top", type=int, default=6, help="检索素材条数")
    p.add_argument("--stdout", action="store_true", help="直接打印，不落盘")
    args = p.parse_args()

    root = course_root()
    text = build_brief(args.kind, args.topic.strip(), root, args.top)

    if args.stdout:
        print(text)
        return 0

    import re
    slug = re.sub(r"[\\/:*?\"<>|\s]+", "-", args.topic.strip())[:40] or "brief"
    out = os.path.join(root, "记录", f"brief-{args.kind}-{slug}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"[ok] 简报已生成：{os.path.relpath(out, root).replace(os.sep, '/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
