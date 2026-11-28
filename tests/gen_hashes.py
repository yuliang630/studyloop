# -*- coding: utf-8 -*-
"""生成 tests/HASHES.txt：基线哈希清单。

CP1 通过时随回执发送审查者外部留存；CP5 以子集判定比对（清单内每个文件
哈希不变 + 新增文件登记）。
"""

from __future__ import annotations

import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "HASHES.txt")
SKIP_DIRS = {"__pycache__", ".work", ".pytest_cache"}


def walk():
    for root, dirs, files in os.walk(HERE):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name == "HASHES.txt":
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, HERE).replace("\\", "/")
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            yield rel, digest


def main() -> int:
    rows = list(walk())
    lines = ["# tests/ 基线哈希清单（CP1 锚点，执行者不得修改）",
             "# 生成命令：python tests/gen_hashes.py",
             ""]
    lines += ["%s  %s" % (digest, rel) for rel, digest in rows]
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("已写入 %s（%d 个文件）" % (OUT, len(rows)))
    for rel, digest in rows:
        print("  %s…  %s" % (digest[:12], rel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
