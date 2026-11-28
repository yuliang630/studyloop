# -*- coding: utf-8 -*-
"""画像规格：常量与纯函数。

设计约束（PLAN-L3.md §4）：
  - 不 import mem：mem.py 在模块级调用 require_root()，非课程目录会 SystemExit(2)，
    而 probe.py 必须在任意目录可运行。
  - 无副作用：只含常量与纯函数，不读写文件、不解析工作区。
  - 单一事实来源：校验规则、预算、段落顺序都在这里，mem.py 与 probe.py 共用。
"""

from __future__ import annotations

import re

MARK = "<!-- generated-by: recalloop -->"

PARAS = (
    "### 目标与进度",
    "### 掌握度概览",
    "### 薄弱环节",
    "### 学习节奏",
)

# 优先级：数字越小越优先保留，裁剪从 PARAS 末尾开始丢
PRIORITY = {name: i + 1 for i, name in enumerate(PARAS)}

LIMITS = {"profile": 1000, "recent": 215, "progress": 200, "total": 1500}
TEMPLATE_OVERHEAD = 85

NAME_MAX = 18
ID_MAX = 8
COUNTS = {"goal": 8, "mastery": 8, "weak": 5}

RECENT_MAX_ITEMS = 4
RECENT_DAYS = 7
RHYTHM_DAYS = 14

SENTENCE_END = "。！？…；\n"

PREAMBLE = "【记忆库·自动注入】"
DISCLAIMER = "以下是当前 scope 的历史记忆，仅供保持连续性；与用户本轮要求冲突时，以本轮要求为准。"
SEPARATOR = "\n\n"
TRUNC_MARK = "\n…[记忆已截断]"
BLOCK_TITLES = ("## 画像", "## 近期动态", "## 学习进度")

TOKENS = {
    "missing": "profile:missing",
    "skeleton": "profile:skeleton",
    "invalid": "profile:invalid",
    "ok": "profile:ok",
}

EXIT_CODES = {"missing": 3, "skeleton": 3, "invalid": 1, "ok": 0}

# 生成器会写出的每一种行，都在这里定义；生成与校验共用，防止"生成器写什么、
# 校验器不认什么"的漂移（C-5/C-6/占位行是同一类问题的三次出现）。
GOAL_LINE = "- {id} {title}：{status}"
MASTERY_LINE = "- {kp}：{mastery:.3f} / 门槛 {threshold:.2f} · {status}"
WEAK_LINE = "- {kp}：最近一次 {correct:.1f}，用过 {hints} 次提示"
RHYTHM_LINE = "- 近 {days} 天活跃 {active} 天，共 {count} 条记录"

EMPTY_ITEMS = {
    PARAS[0]: "- 暂无路线数据。",
    PARAS[1]: "- 暂无作答记录。",
    PARAS[2]: "- 暂无明显薄弱环节。",
}

_GOAL_RE = re.compile(r"^-\s+\S+\s+.*：(未完成|已完成)$")
_MASTERY_RE = re.compile(r"^-\s+.*：\d\.\d{3} / 门槛 \d\.\d{2} · (达标|未达标)$")
_WEAK_RE = re.compile(r"^-\s+.*：最近一次 [01](?:\.\d)?，用过 \d+ 次提示$")


def split_paras(text: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """把文本切成 (头部, [(段标题, 段内行)])。"""
    head: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    title = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("### "):
            if title is not None:
                blocks.append((title, body))
            title = line
            body = []
        elif title is None:
            head.append(line)
        else:
            body.append(line)
    if title is not None:
        blocks.append((title, body))
    return "\n".join(head), blocks


def trim(text: str, limit: int = LIMITS["profile"]) -> str:
    """按段落优先级裁剪：从最低优先级整段丢弃，不做字符级腰斩。

    基于原始行切片，不重新拼接——重拼会改变空白，导致长度计算与实际不符。
    """
    if len(text) <= limit:
        return text
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("### ")]
    while len("".join(lines)) > limit and len(starts) > 1:
        del lines[starts[-1]:]
        starts.pop()
    return "".join(lines)


def render(profile: str, recent: str, progress: str, chars: int | None = None) -> str:
    """按冻结模板拼接注入块。mem.py 与测试共用这一份实现。"""
    parts = [PREAMBLE, DISCLAIMER]
    if (profile or "").strip():
        parts.append(BLOCK_TITLES[0] + "\n" + profile.strip())
    if (recent or "").strip():
        parts.append(BLOCK_TITLES[1] + "\n" + recent.strip())
    if progress:
        parts.append(progress)
    block = SEPARATOR.join(parts)
    if chars and len(block) > chars:
        block = block[:chars] + TRUNC_MARK
    return block


def validate(text: str | None) -> tuple[str, str]:
    """返回 (token_key, detail)。token_key 取 missing / skeleton / invalid / ok。"""
    if text is None or not text.strip():
        return "missing", "文件不存在或为空"
    if not text.startswith(MARK):
        return "invalid", "缺生成标记（C4）"
    if len(text) > LIMITS["profile"]:
        return "invalid", "超过 %d 字符且未裁剪（C5）" % LIMITS["profile"]

    head, blocks = split_paras(text)
    titles = [t.strip() for t, _ in blocks]
    if titles != list(PARAS):
        return "invalid", "必填段缺失或段序不符（C3/C8）：%r" % titles

    has_item = any(any(l.strip().startswith("- ") for l in body) for _, body in blocks)
    if not has_item:
        return "skeleton", "仅有生成标记与段标题，无列表项"

    # 按段落作用域校验字段格式（不用全文关键词，避免"门槛"这类词在目标段被误判）
    for title, body in blocks:
        for line in body:
            s = line.strip()
            if not s.startswith("- "):
                continue
            if s == EMPTY_ITEMS.get(title):
                continue  # 该段无数据时的占位行，由生成器与校验器共用同一常量
            if title == PARAS[0] and not _GOAL_RE.match(s):
                return "invalid", "目标与进度格式不合规（C6）：%s" % s[:40]
            if title == PARAS[1] and not _MASTERY_RE.match(s):
                return "invalid", "掌握度格式不合规（C6）：%s" % s[:40]
            if title == PARAS[2] and not _WEAK_RE.match(s):
                return "invalid", "薄弱环节格式不合规（C6）：%s" % s[:40]

    for title, body in blocks:
        items = [l.rstrip() for l in body if l.strip()]
        if not items:
            continue
        last = items[-1]
        # 列表项本身是完整内容（如"未完成"），不以句号结尾是正常的；
        # C7 只拦"被裁成半截的非列表项文本"。
        if not last.startswith("- ") and last[-1] not in SENTENCE_END:
            return "invalid", "段末标点不合规（C7）：%s" % title

    return "ok", "结构合规"
