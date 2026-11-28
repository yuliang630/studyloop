# -*- coding: utf-8 -*-
"""重新生成 tests/samples/ 下的四个 profile 样本。

S-valid 按 schema 冻结的**上限**构造（8/8/5/1 条、字段 18 字符），因此它是
"最坏合规样本"——长度由结构决定（约 840 字符），不是硬编码的 1000。

原因：schema 的条数与字段上限正是为了把最坏长度压到 1000 以下（A4 要求
k≥1）。所以"恰好 1000 字符且完全合规"在冻结规格下不可达；A5 验证的是
"不超预算时不裁剪"，用最坏合规样本即可，不需要精确 1000。

用法：python tests/gen_samples.py
生成后必须重新运行 `python tests/gen_hashes.py` 更新 HASHES.txt。
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")

MARK = "<!-- generated-by: recalloop -->\n\n"
S2_HEAD = "### 掌握度概览\n"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _pad(text: str, width: int = 18) -> str:
    """把名称填充到固定宽度（不超过字段上限）。"""
    return text if len(text) >= width else text + "补" * (width - len(text))


def make_valid() -> str:
    """按 schema 上限构造的最坏合规样本。"""
    s1 = "### 目标与进度\n"
    for i in range(8):
        s1 += "- %02d %s：未完成\n" % (i + 1, _pad("导数定义"))
    s1 += "\n"

    s2 = S2_HEAD
    for i in range(8):
        s2 += "- %s：0.500 / 门槛 0.95 · 未达标\n" % _pad("知识点%02d" % i)
    s2 += "\n"

    s3 = "### 薄弱环节\n"
    for i in range(5):
        s3 += "- %s：最近一次 0.5，用过 2 次提示\n" % _pad("知识点%02d" % i)
    s3 += "\n"

    s4 = "### 学习节奏\n- 近 14 天活跃 5 天，共 23 条记录\n"
    return MARK + s1 + s2 + s3 + s4


def make_skeleton() -> str:
    return MARK + "### 目标与进度\n\n### 掌握度概览\n\n### 薄弱环节\n\n### 学习节奏\n"


def make_invalid() -> str:
    """结构错误：缺必填段（薄弱环节）、掌握度格式不合规、段序错误。"""
    return (
        MARK
        + "### 目标与进度\n- 01 导数定义：未完成\n\n"
        + "### 掌握度概览\n- 导数定义：0.5 / 门槛 0.95\n\n"
        + "### 学习节奏\n- 近 14 天活跃 3 天\n"
    )


def main() -> int:
    valid = make_valid()
    _write(os.path.join(SAMPLES, "S-valid", "profile.md"), valid)
    _write(os.path.join(SAMPLES, "S-skeleton", "profile.md"), make_skeleton())
    _write(os.path.join(SAMPLES, "S-invalid", "profile.md"), make_invalid())
    _write(os.path.join(SAMPLES, "S-zero", "profile.md"), "")
    for name in ("S-zero", "S-skeleton", "S-invalid", "S-valid"):
        p = os.path.join(SAMPLES, name, "profile.md")
        with open(p, encoding="utf-8") as f:
            n = len(f.read())
        print("%-12s %d 字符" % (name, n))
    print("S-valid 必须 ≤1000：%s" % ("通过" if len(valid) <= 1000 else "失败"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
