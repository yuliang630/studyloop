#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物脚手架：新建 / 列出学习产物（试卷、教案、讲义、课程规划）。

只做结构与路径，不写内容。内容由 agent 填。

用法（必须在课程目录下运行）：
    python artifacts.py new exam --topic "第01课 认识ComfyUI"
    python artifacts.py new lesson --topic "..."
    python artifacts.py new handout --topic "..."
    python artifacts.py new curriculum --topic "ComfyUI 入门"
    python artifacts.py list
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(SCRIPTS))
TEMPLATES = os.path.join(PACK, "core", "skills", "study-loop", "templates")

KINDS = {
    "exam": {"tpl": "exam.md", "name": "{date}-{slug}.md", "title": "试卷", "title_en": "Exam"},
    "lesson": {"tpl": "lesson.md", "name": "{date}-{slug}.md", "title": "教案", "title_en": "Lesson plan"},
    "handout": {"tpl": "handout.md", "name": "{slug}.md", "title": "讲义", "title_en": "Handout"},
    "curriculum": {"tpl": "curriculum.md", "name": "课程规划.md", "title": "课程规划", "title_en": "Curriculum"},
}

# 默认落点；可被 .study-workspace 的 layout 字段覆盖
DEFAULT_LAYOUT = {
    "exam": "题库/考试卷",
    "lesson": "笔记/教案",
    "handout": "笔记/讲义",
    "curriculum": "记录",
    "bank": "题库/index.jsonl",
}

LAYOUT_DOC = {
    "exam": "试卷",
    "lesson": "教案",
    "handout": "讲义",
    "curriculum": "课程规划",
    "bank": "题库索引",
}

META_RE = re.compile(r"<!--\s*artifact:\s*([a-z]+);\s*status:\s*([a-z]+);.*?topic:\s*(.*?);\s*date:\s*([\d-]+)")


def course_root() -> str:
    root = os.getcwd()
    if not os.path.exists(os.path.join(root, ".study-workspace")):
        raise SystemExit("[error] 当前目录不是课程工作区（缺 .study-workspace）；请先 cd 到课程目录")
    return root


def course_name(root: str) -> str:
    try:
        with open(os.path.join(root, ".study-workspace"), "r", encoding="utf-8-sig") as f:
            return str(json.load(f).get("name") or os.path.basename(root))
    except Exception:
        return os.path.basename(root)


def slugify(text: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "-", text.strip())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:60] or "untitled"


def effective_layout(root: str) -> dict:
    """默认布局 + .study-workspace 里的 layout 覆盖。"""
    lay = dict(DEFAULT_LAYOUT)
    try:
        with open(os.path.join(root, ".study-workspace"), "r", encoding="utf-8-sig") as f:
            marker = json.load(f)
        override = marker.get("layout") or {}
        for k, v in override.items():
            if k in lay and isinstance(v, str) and v.strip():
                lay[k] = v.strip().replace("\\", "/")
    except Exception:
        pass
    return lay


def cmd_layout(args) -> int:
    """打印当前工作区生效的布局，并标出缺哪些目录（只报告，不创建）。"""
    root = course_root()
    lay = effective_layout(root)
    marker_path = os.path.join(root, ".study-workspace")
    try:
        with open(marker_path, "r", encoding="utf-8-sig") as f:
            overridden = set((json.load(f).get("layout") or {}).keys())
    except Exception:
        overridden = set()

    print(f"工作区：{root}")
    print(f"课程名：{course_name(root)}")
    print()
    print(f"{'产物':<12} {'落点':<26} {'目录':<6} 来源")
    print("-" * 70)
    for key, label in LAYOUT_DOC.items():
        path = lay[key]
        full = os.path.join(root, path)
        exists = "有" if os.path.exists(full) else "缺"
        src = "覆盖" if key in overridden else "默认"
        print(f"{label:<12} {path:<26} {exists:<6} {src}")
    print()
    print("说明：")
    print("  - 目录缺失不影响使用，`artifacts.py new` 会自动创建它涉及的目录")
    print("  - 想改落点：在 .study-workspace 里加 layout 字段（见 references/layout.md）")
    return 0


def artifact_path(root: str, kind: str, topic: str, date: str) -> str:
    spec = KINDS[kind]
    name = spec["name"].format(date=date, slug=slugify(topic))
    return os.path.join(root, effective_layout(root)[kind], name)


def workspace_lang(root: str) -> str:
    """.study-workspace 里的 lang 字段决定默认模板语言；没写就是 zh。"""
    try:
        with open(os.path.join(root, ".study-workspace"), "r", encoding="utf-8-sig") as f:
            v = str(json.load(f).get("lang") or "").strip().lower()
        return v if v in ("zh", "en") else "zh"
    except Exception:
        return "zh"


def template_path(kind: str, lang: str) -> str:
    base = os.path.join(TEMPLATES, "en") if lang == "en" else TEMPLATES
    return os.path.join(base, KINDS[kind]["tpl"])


def cmd_new(args) -> int:
    root = course_root()
    kind = args.kind
    if kind not in KINDS:
        print(f"[error] 未知类型：{kind}", file=sys.stderr)
        return 2
    topic = args.topic.strip()
    if not topic:
        print("[error] --topic 不能为空", file=sys.stderr)
        return 2

    date = args.date or dt.date.today().isoformat()
    lang = (getattr(args, "lang", None) or workspace_lang(root))
    tpl_path = template_path(kind, lang)
    if not os.path.exists(tpl_path):
        print(f"[error] 模板不存在：{tpl_path}", file=sys.stderr)
        return 2

    target = artifact_path(root, kind, topic, date)
    if os.path.exists(target) and not args.force:
        print(f"[error] 已存在：{target}\n        加 --force 覆盖", file=sys.stderr)
        return 2

    with open(tpl_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = (text.replace("{{topic}}", topic)
                .replace("{{date}}", date)
                .replace("{{course}}", course_name(root))
                .replace("{{title}}", f"{KINDS[kind]['title']}：{topic}"))

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)

    rel = os.path.relpath(target, root).replace(os.sep, "/")
    if lang == "en":
        print(f"[ok] Created {KINDS[kind]['title_en']}: {rel}")
        print("     next: fill the middleware (blueprint / outline / glossary) before writing the body")
    else:
        print(f"[ok] 已创建 {KINDS[kind]['title']}：{rel}")
        print("     下一步：先填中间件（蓝图/大纲/术语表），再写正文")
    return 0


def _read_meta(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            head = f.read(600)
    except Exception:
        return {}
    m = META_RE.search(head)
    if not m:
        return {}
    return {"kind": m.group(1), "status": m.group(2), "topic": m.group(3), "date": m.group(4)}


def cmd_list(args) -> int:
    root = course_root()
    links: dict[str, str] = {}
    try:
        pj = os.path.join(root, "记忆", "data", "state", "path.json")
        if os.path.exists(pj):
            data = json.load(open(pj, "r", encoding="utf-8-sig"))
            for it in data.get("items", []):
                if it.get("artifact"):
                    links[it["artifact"]] = it.get("id", "")
    except Exception:
        pass

    rows = []
    lay = effective_layout(root)
    for kind, spec in KINDS.items():
        d = os.path.join(root, lay[kind])
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(d, name)
            meta = _read_meta(path)
            rows.append({
                "kind": kind,
                "path": os.path.relpath(path, root).replace(os.sep, "/"),
                "status": meta.get("status", "?"),
                "date": meta.get("date", ""),
                "size": os.path.getsize(path),
            })
    if not rows:
        print("（还没有任何产物。用 artifacts.py new <类型> --topic \"...\" 创建）")
        return 0
    print(f"{'类型':<10} {'状态':<8} {'日期':<12} {'挂接':<6} 路径")
    print("-" * 84)
    for r in rows:
        print(f"{KINDS[r['kind']]['title']:<10} {r['status']:<8} {r['date']:<12} {links.get(r['path'], '-'):<6} {r['path']}")
    print(f"\n共 {len(rows)} 份")
    return 0



# ---------------------------------------------------------------- 校验

REQUIRED = {
    "exam": ["命题蓝图", "题目", "答案与评分点", "来源"],
    "lesson": ["目标", "难点", "例子", "验收题", "预计时长", "前置", "来源"],
    "handout": ["术语表", "大纲", "参考"],
    "curriculum": ["目标", "起点", "知识点表", "依赖检查", "排期", "来源"],
}

# 段名别名：中文是规范名，英文写法同样被接受（另一个语言的人不用改校验器）
ALIASES = {
    "命题蓝图": ["exam blueprint", "blueprint", "test blueprint"],
    "题目": ["questions", "question"],
    "答案与评分点": ["answers and scoring points", "answers and scoring", "answers & scoring", "answers"],
    "来源": ["sources", "source", "references", "reference"],
    "参考": ["references", "reference", "sources", "source"],
    "目标": ["objectives", "objective", "goals", "goal"],
    "难点": ["difficult points", "difficulty", "pain points", "sticking points"],
    "例子": ["examples", "example", "worked example"],
    "验收题": ["acceptance questions", "check questions", "check-question set"],
    "预计时长": ["estimated duration", "duration", "time needed"],
    "前置": ["prerequisites", "prerequisite"],
    "术语表": ["glossary", "terms"],
    "大纲": ["outline", "structure"],
    "起点": ["starting point", "starting level", "baseline"],
    "知识点表": ["knowledge point table", "knowledge points", "topic table"],
    "依赖检查": ["dependency check", "dependencies", "dependency graph"],
    "排期": ["schedule", "timeline", "plan"],
}

NUM_PREFIX = re.compile(r"^[一二三四五六七八九十百0-9]+\s*[、.．]\s*")

PLACEHOLDER = re.compile(r"^\s*[（(].*[)）]\s*$")


def split_sections(text: str) -> dict:
    """按二级标题切段，返回 {标题: 正文}。"""
    out = {}
    cur = None
    buf = []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur = NUM_PREFIX.sub("", line[3:].strip())
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def meaningful_lines(body: str) -> list[str]:
    """去掉占位符、空行、表头分隔后的有效行。"""
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if PLACEHOLDER.match(s):
            continue
        if set(s) <= set("-|: "):
            continue
        if re.match(r"^-\s*[A-D]\.\s*$", s):
            continue
        if re.match(r"^-\s*(答案|评分点|answer|scoring points?|points?)\s*[:：]\s*$", s, re.I):
            continue
        if re.match(r"^\d+\.\s*$", s):
            continue
        if len(re.sub(r"[\s\-|*#：:]", "", s)) < 2:
            continue
        out.append(s)
    return out


def _norm_head(s: str) -> str:
    return re.sub(r"[\s_*`#]+", " ", s.strip().lower())


def section(sections: dict, name: str) -> str:
    """按规范名找段落；找不到就按英文别名找（两种语言的产物都能校验）。"""
    wanted = [_norm_head(name)] + [_norm_head(a) for a in ALIASES.get(name, [])]
    for k, v in sections.items():
        kk = _norm_head(k)
        if any(kk.startswith(w) for w in wanted if w):
            return v
    return ""


def parse_blueprint(body: str) -> list[dict]:
    rows = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0] in ("知识点", "") or _norm_head(cells[0]) in (
                "knowledge point", "topic", "kp", "") or set(cells[0]) <= set("-: "):
            continue
        try:
            n = int(re.sub(r"\D", "", cells[3]) or "0")
        except Exception:
            n = 0
        rows.append({"kp": cells[0], "type": cells[1], "count": n})
    return rows


def parse_questions(body: str) -> list[str]:
    heads = []
    for line in body.splitlines():
        m = re.match(r"^###\s+(.*)$", line.strip())
        if m:
            heads.append(m.group(1))
    return heads


def parse_answers(body: str) -> list[str]:
    blocks = []
    cur = []
    for line in body.splitlines():
        if line.strip().startswith("### "):
            if cur:
                blocks.append("\n".join(cur))
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def cmd_check(args) -> int:
    root = course_root()
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print(f"[error] 文件不存在：{args.file}", file=sys.stderr)
        return 2
    text = open(path, "r", encoding="utf-8-sig", errors="replace").read()

    meta = _read_meta(path)
    kind = args.kind or meta.get("kind") or ""
    if kind not in REQUIRED:
        print("[error] 无法判断产物类型（元数据缺 artifact:），用 --kind 指定", file=sys.stderr)
        return 2

    sections = split_sections(text)
    problems: list[str] = []

    # 1) 必填段
    for name in REQUIRED[kind]:
        body = section(sections, name)
        if not body:
            problems.append(f"缺少段落：## {name}")
        elif not meaningful_lines(body):
            problems.append(f"段落为空：## {name}")

    # 2) 试卷专属
    if kind == "exam":
        bp_body = section(sections, "命题蓝图")
        rows = parse_blueprint(bp_body)
        if not rows:
            problems.append("命题蓝图为空")
        qs = parse_questions(section(sections, "题目"))
        ans = parse_answers(section(sections, "答案与评分点"))

        total = sum(r["count"] for r in rows) or len(rows)
        if len(qs) == 0:
            problems.append("没有任何题目（### 标题）")
        elif total and len(qs) != total:
            problems.append(f"题量与蓝图不一致：蓝图 {total}，实际 {len(qs)}")

        for r in rows:
            if not any(r["kp"] in h for h in qs):
                problems.append(f"蓝图知识点未被覆盖：{r['kp']}")

        if len(ans) != len(qs):
            problems.append(f"答案条目数 {len(ans)} 与题目数 {len(qs)} 不一致")
        for i, block in enumerate(ans, 1):
            if not re.search(r"(答案|answer)\s*[:：]\s*\S", block, re.I):
                problems.append(f"第 {i} 题缺答案")
            if not re.search(r"(评分点|scoring( points?)?|points?)\s*[:：]\s*\S", block, re.I):
                problems.append(f"第 {i} 题缺评分点")

    # 3) 讲义分章引用（中英文章节名都认）
    if kind == "handout":
        chapters = [k for k in sections
                    if (k.startswith("第") and "章" in k) or re.match(r"^chapter\s*\d+", k, re.I)]
        if not chapters:
            problems.append("讲义没有任何章节（## 第X章 / ## Chapter N）")
        for ch in chapters:
            body = sections[ch]
            if not re.search(r"\*\*(来源|source)\*\*\s*[:：]\s*(?![（(])\S", body, re.I):
                problems.append(f"章节缺来源：{ch}")

    # 4) 来源段必须真有内容
    src = section(sections, "来源") or section(sections, "参考")
    if src and not meaningful_lines(src):
        problems.append("来源/参考段为空")

    if problems:
        print(f"[fail] {os.path.relpath(path, root).replace(os.sep, '/')}")
        for p_ in problems:
            print(f"       - {p_}")
        print(f"\n共 {len(problems)} 个问题")
        return 1
    print(f"[ok] 通过：{os.path.relpath(path, root).replace(os.sep, '/')}")
    return 0



# ---------------------------------------------------------------- 回写

BANK = os.path.join("题库", "index.jsonl")


def parse_question_blocks(body: str) -> list[dict]:
    """把「题目」段拆成结构化条目。"""
    blocks = []
    cur = None
    for line in body.splitlines():
        m = re.match(r"^###\s+(.*)$", line.strip())
        if m:
            if cur:
                blocks.append(cur)
            cur = {"head": m.group(1), "lines": []}
        elif cur is not None:
            cur["lines"].append(line)
    if cur:
        blocks.append(cur)
    return blocks


def parse_answer_blocks(body: str) -> dict:
    """把「答案与评分点」段拆成 {题号: (答案, 评分点)}。"""
    out = {}
    cur_no = None
    for line in body.splitlines():
        m = re.match(r"^###\s+(\d+)", line.strip())
        if m:
            cur_no = int(m.group(1))
            out[cur_no] = {"answer": "", "points": ""}
            continue
        if cur_no is None:
            continue
        ma = re.match(r"^-\s*(答案|answer)\s*[:：]\s*(.*)$", line.strip(), re.I)
        mp = re.match(r"^-\s*(评分点|scoring( points?)?|points?)\s*[:：]\s*(.*)$", line.strip(), re.I)
        if ma:
            out[cur_no]["answer"] = ma.group(2).strip()
        elif mp:
            out[cur_no]["points"] = mp.group(3).strip()
    return out


def cmd_bank(args) -> int:
    """把试卷题目抽成结构化条目写入 题库/index.jsonl（幂等）。"""
    root = course_root()
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print(f"[error] 文件不存在：{args.file}", file=sys.stderr)
        return 2
    text = open(path, "r", encoding="utf-8-sig", errors="replace").read()
    sections = split_sections(text)
    q_blocks = parse_question_blocks(section(sections, "题目"))
    answers = parse_answer_blocks(section(sections, "答案与评分点"))
    if not q_blocks:
        print("[error] 没解析到题目（### 标题）", file=sys.stderr)
        return 1

    rel = os.path.relpath(path, root).replace(os.sep, "/")
    lay = effective_layout(root)
    rel_bank = lay["bank"]
    bank_path = os.path.join(root, rel_bank)
    existing = []
    if os.path.exists(bank_path):
        with open(bank_path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing.append(json.loads(line))
                    except Exception:
                        continue
    seen = {(e.get("exam"), e.get("no")) for e in existing}

    added = 0
    for i, blk in enumerate(q_blocks, 1):
        if (rel, i) in seen:
            continue
        head = blk["head"]
        head = re.sub(r"^\d+\.\s*", "", head).strip("（）() ")
        meta = [x.strip("（）() ") for x in head.split("/")]
        kp = meta[-1] if len(meta) >= 3 else ""
        qtype = meta[0] if len(meta) >= 3 else ""
        difficulty = meta[1] if len(meta) >= 3 else ""
        stem = ""
        options = []
        for line in blk["lines"]:
            s = line.strip()
            if s.startswith("题干"):
                stem = s.split("：", 1)[-1].strip()
            elif re.match(r"^-\s*[A-D]\.", s):
                options.append(s[1:].strip())
        a = answers.get(i, {})
        existing.append({
            "v": 1,
            "exam": rel,
            "no": i,
            "kp": kp,
            "type": qtype,
            "difficulty": difficulty,
            "stem": stem,
            "options": options,
            "answer": a.get("answer", ""),
            "points": a.get("points", ""),
        })
        added += 1

    os.makedirs(os.path.dirname(bank_path), exist_ok=True)
    with open(bank_path, "w", encoding="utf-8") as f:
        for e in existing:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"[ok] 题库条目：新增 {added}，总计 {len(existing)} → {rel_bank}")
    return 0


def cmd_link(args) -> int:
    """把产物挂到知识点路径条目上（写 path.json 的 artifact 字段）。"""
    root = course_root()
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print(f"[error] 文件不存在：{args.file}", file=sys.stderr)
        return 2
    pj = os.path.join(root, "记忆", "data", "state", "path.json")
    if not os.path.exists(pj):
        print("[error] 还没有路径（先跑 path.py init）", file=sys.stderr)
        return 2
    data = json.load(open(pj, "r", encoding="utf-8-sig"))
    target = next((x for x in data.get("items", []) if x.get("id") == args.id.zfill(2)), None)
    if not target:
        print(f"[error] 路径里没有 id={args.id}", file=sys.stderr)
        return 2
    target["artifact"] = os.path.relpath(path, root).replace(os.sep, "/")
    tmp = pj + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, pj)
    print(f"[ok] 已挂到 {target['id']} {target['title']} → {target['artifact']}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="artifacts.py", description="学习产物脚手架")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="新建产物")
    n.add_argument("kind", choices=sorted(KINDS))
    n.add_argument("--topic", required=True)
    n.add_argument("--date", default=None, help="默认今天")
    n.add_argument("--lang", default=None, choices=["zh", "en"], help="模板语言，默认取工作区 lang 或 zh")
    n.add_argument("--force", action="store_true")

    sub.add_parser("list", help="列出已有产物")
    sub.add_parser("layout", help="打印当前工作区生效的目录布局")

    c = sub.add_parser("check", help="校验产物结构")
    c.add_argument("file")
    c.add_argument("--kind", default=None, choices=sorted(KINDS))

    b = sub.add_parser("bank", help="把试卷题目写入题库索引")
    b.add_argument("file")

    lk = sub.add_parser("link", help="把产物挂到路径条目")
    lk.add_argument("file")
    lk.add_argument("--id", required=True)

    args = p.parse_args()
    if args.cmd == "new":
        return cmd_new(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "layout":
        return cmd_layout(args)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "bank":
        return cmd_bank(args)
    if args.cmd == "link":
        return cmd_link(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
