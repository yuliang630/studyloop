#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装辅助：写可选的本机偏好到 config.json。

包可以在任意目录运行：所有脚本都用自身位置定位包根目录，**不记录任何本机绝对路径**。
config.json 只保存可选项（目前只有 default_workspace），没有可选项时就不需要它。

手动用法：
    python core\\scripts\\setup_config.py
    python core\\scripts\\setup_config.py --workspace "D:\\courses\\calculus"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(SCRIPTS))
CONFIG = os.path.join(PACK, "config.json")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", default=None, help="默认课程工作区（可选）")

    args = p.parse_args()

    data = {}
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # 老版本写入的本机路径，一律清掉：包搬到哪都能跑，不需要记住
    for stale in ("pack_root", "scripts_dir", "courses_root"):
        data.pop(stale, None)

    data["v"] = 1

    if args.workspace:
        data["default_workspace"] = os.path.abspath(args.workspace)
    elif "default_workspace" not in data:
        data["default_workspace"] = ""

    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"config 已写入：{CONFIG}")
    print(f"  包根目录    {PACK}（不写进 config，脚本按自身位置定位）")
    print(f"  workspace  {data.get('default_workspace') or '（未设置，按当前目录判断）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
