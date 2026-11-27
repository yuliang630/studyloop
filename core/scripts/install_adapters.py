#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装适配器：把包里的钩子放到目标 agent 的固定目录。

只自动安装确定安全的（OpenCode 插件目录）。
Claude Code 系需要改 settings.json，不自动改，只打印该贴什么。
"""

from __future__ import annotations

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(SCRIPTS))
HOME = os.path.expanduser("~")


def install_opencode() -> bool:
    src = os.path.join(PACK, "adapters", "opencode", "memory.ts")
    dst_dir = os.path.join(HOME, ".config", "opencode", "plugins")
    if not os.path.exists(src):
        print("  [跳过] 包里没有 adapters\\opencode\\memory.ts")
        return False
    if not os.path.isdir(os.path.dirname(dst_dir)):
        print("  [跳过] 本机没有 OpenCode 配置目录")
        return False
    os.makedirs(dst_dir, exist_ok=True)
    with open(src, "r", encoding="utf-8") as f:
        code = f.read()
    pack_js = PACK.replace("\\", "/")
    code = code.replace("__PACK_ROOT__", pack_js)
    dst = os.path.join(dst_dir, "memory.ts")
    existed = os.path.exists(dst)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"  [{'覆盖' if existed else '安装'}] {dst}")
    return True


def show_claude_hooks() -> None:
    src = os.path.join(PACK, "adapters", "claude-code", "hooks.json")
    if not os.path.exists(src):
        return
    with open(src, "r", encoding="utf-8") as f:
        text = f.read().replace("__PACK_ROOT__", PACK.replace("\\", "\\\\"))
    print()
    print("  Claude Code / CodeBuddy：需要把这部分合并进 settings.json 的 hooks 字段：")
    print()
    for line in text.splitlines():
        print("    " + line)
    print()


def install_skills() -> bool:
    """把技能装到 OpenCode，并把 <PACK> 换成真实路径（否则 agent 找不到脚本）。"""
    src_root = os.path.join(PACK, "core", "skills")
    dst_root = os.path.join(HOME, ".config", "opencode", "skills")
    if not os.path.isdir(src_root):
        return False
    if not os.path.isdir(os.path.dirname(dst_root)):
        print("  [跳过] 本机没有 OpenCode 技能目录")
        return False
    installed = False
    for name in os.listdir(src_root):
        src = os.path.join(src_root, name, "SKILL.md")
        if not os.path.isfile(src):
            continue
        dst_dir = os.path.join(dst_root, name)
        os.makedirs(dst_dir, exist_ok=True)
        with open(src, "r", encoding="utf-8") as f:
            text = f.read().replace("<PACK>", PACK)
        with open(os.path.join(dst_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  [安装] {os.path.join(dst_dir, 'SKILL.md')}")
        # 附属文件（references/*.md）也要装，否则 SKILL.md 里的相对路径指向空
        ref_src = os.path.join(src_root, name, "references")
        if os.path.isdir(ref_src):
            ref_dst = os.path.join(dst_dir, "references")
            os.makedirs(ref_dst, exist_ok=True)
            for fn in os.listdir(ref_src):
                if not fn.lower().endswith(".md"):
                    continue
                with open(os.path.join(ref_src, fn), "r", encoding="utf-8") as f:
                    body = f.read().replace("<PACK>", PACK)
                with open(os.path.join(ref_dst, fn), "w", encoding="utf-8") as f:
                    f.write(body)
                print(f"  [安装] {os.path.join(ref_dst, fn)}")
        installed = True
    return installed


def main() -> int:
    print("== 安装适配器 ==")
    installed = False
    if os.path.isdir(os.path.join(HOME, ".config", "opencode")):
        installed = install_opencode() or installed
        installed = install_skills() or installed
    else:
        print("  [跳过] 未检测到 OpenCode")

    if os.path.isdir(os.path.join(HOME, ".claude")):
        show_claude_hooks()

    print()
    print("  通用用法见 adapters\\generic\\README.md")
    print("  完成" if installed else "  未安装任何自动适配器（不影响用命令行）")
    print()
    print("  若已在 agent 中打开，请重启它，让钩子加载。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
