#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装适配器：把钩子与技能装进**你指定的那个** agent，一个字节都不碰别人的目录。

设计约束（v2.1.0 重写）：
    1. 没有"探测到谁就顺手装给谁"的逻辑。默认按当前运行环境判断宿主；判断不出来就只打印，不写。
    2. 只在**已经存在**的宿主配置根里写；不会凭空创建别人的配置目录。
    3. 不认识的文件绝不覆盖：目标文件里没有本插件的标记就不动，报冲突并给出手工办法。
    4. 想强制覆盖必须显式 --force，且先备份成 <文件名>.bak-<时间戳>。

用法：
    python core\\scripts\\install_adapters.py                     # 按当前宿主自动判断
    python core\\scripts\\install_adapters.py --target opencode
    python core\\scripts\\install_adapters.py --target claude
    python core\\scripts\\install_adapters.py --target workbuddy
    python core\\scripts\\install_adapters.py --target generic --skills-dir "D:\\my-agent\\skills"
    python core\\scripts\\install_adapters.py --target none        # 只看诊断，不装

退出码：0 正常（含"判断不出宿主，只给说明"）；2 用法错误；3 有文件冲突未写入。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(SCRIPTS))
HOME = os.path.expanduser("~")

MARK_TS = "// @studyloop-managed"
MARK_MD = "<!-- @studyloop-managed -->"

# 每个宿主：怎么认出来、配置根在哪、钩子怎么装
HOSTS = {
    "opencode": {
        "label": "OpenCode",
        "root": os.path.join(HOME, ".config", "opencode"),
        "skills": os.path.join(HOME, ".config", "opencode", "skills"),
        "plugins": os.path.join(HOME, ".config", "opencode", "plugins"),
        "hook": "plugin",
    },
    "claude": {
        "label": "Claude Code / CodeBuddy",
        "root": os.path.join(HOME, ".claude"),
        "skills": os.path.join(HOME, ".claude", "skills"),
        "plugins": None,
        "hook": "print-json",
    },
    "workbuddy": {
        "label": "WorkBuddy",
        "root": os.path.join(HOME, ".workbuddy"),
        "skills": os.path.join(HOME, ".workbuddy", "skills"),
        "plugins": None,
        "hook": "manual",
    },
}

ENV_SIGNALS = [
    ("opencode", ("OPENCODE_SESSION_ID", "OPENCODE")),
    ("claude", ("CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE", "CLAUDE_CODE_SSE_PORT")),
    ("workbuddy", ("WORKBUDDY_HOME", "WORKBUDDY_SESSION_ID", "WORKBUDDY")),
]

MANUAL_HINT = [
    "开课时（把画像与进度注入上下文）：",
    "  python <PACK>\\core\\scripts\\mem.py inject",
    "一轮结束后（把这一轮写进 L1）：",
    "  python <PACK>\\core\\scripts\\mem.py ingest --file <对话记录文件>",
    "其余命令（检索、判分、出题）在任何能跑命令的 agent 里都一样。",
]


def detect_host() -> tuple[str, str]:
    """按当前进程环境判断宿主，返回 (target, 依据)。判断不出返回 ("", "")。"""
    for target, names in ENV_SIGNALS:
        for n in names:
            if os.environ.get(n):
                return target, f"环境变量 {n}"
    return "", ""


def read_head(path: str, limit: int = 4000) -> str:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def is_ours(path: str, mark: str) -> bool:
    return mark in read_head(path)


def backup(path: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = f"{path}.bak-{stamp}"
    shutil.copy2(path, dst)
    return dst


class Result:
    def __init__(self) -> None:
        self.written: list[str] = []
        self.skipped: list[str] = []
        self.conflicts: list[str] = []


def put_file(path: str, content: str, mark: str, force: bool, res: Result) -> None:
    """写一个文件：不存在就写；是本插件的就更新；别人的不碰。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        if is_ours(path, mark):
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            res.written.append(path)
            return
        if not force:
            res.conflicts.append(path)
            return
        saved = backup(path)
        print(f"       已备份 -> {os.path.basename(saved)}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    res.written.append(path)


def install_skill(skill_dir: str, force: bool, res: Result) -> None:
    """装技能本体 + references，全部替换 <PACK>。"""
    src_root = os.path.join(PACK, "core", "skills")
    if not os.path.isdir(src_root):
        res.skipped.append(f"{src_root}（包里没有技能目录）")
        return
    for name in sorted(os.listdir(src_root)):
        src = os.path.join(src_root, name, "SKILL.md")
        if not os.path.isfile(src):
            continue
        dst_dir = os.path.join(skill_dir, name)
        with open(src, "r", encoding="utf-8") as f:
            put_file(os.path.join(dst_dir, "SKILL.md"),
                     f.read().replace("<PACK>", PACK), MARK_MD, force, res)
        ref_src = os.path.join(src_root, name, "references")
        if os.path.isdir(ref_src):
            for fn in sorted(os.listdir(ref_src)):
                if not fn.lower().endswith(".md"):
                    continue
                with open(os.path.join(ref_src, fn), "r", encoding="utf-8") as f:
                    put_file(os.path.join(dst_dir, "references", fn),
                             f.read().replace("<PACK>", PACK), MARK_MD, force, res)


def install_opencode_plugin(target: dict, force: bool, res: Result) -> None:
    src = os.path.join(PACK, "adapters", "opencode", "memory.ts")
    if not os.path.isfile(src):
        res.skipped.append(f"{src}（包里没有 OpenCode 适配器）")
        return
    with open(src, "r", encoding="utf-8") as f:
        code = f.read().replace("__PACK_ROOT__", PACK.replace("\\", "/"))
    put_file(os.path.join(target["plugins"], "memory.ts"), code, MARK_TS, force, res)


def show_claude_hooks() -> None:
    src = os.path.join(PACK, "adapters", "claude-code", "hooks.json")
    if not os.path.isfile(src):
        return
    with open(src, "r", encoding="utf-8") as f:
        text = f.read().replace("__PACK_ROOT__", PACK.replace("\\", "\\\\"))
    print()
    print("  Claude Code / CodeBuddy 的钩子需要你手工合并进 settings.json 的 hooks 字段：")
    print()
    for line in text.splitlines():
        print("    " + line)
    print()


def print_manual() -> None:
    print()
    print("  手动用法（任何能跑命令的 agent 都适用）：")
    for line in MANUAL_HINT:
        print("    " + line.replace("<PACK>", PACK))


def do_install(target_name: str, args, res: Result) -> int:
    target = HOSTS[target_name]
    root = target["root"]
    print(f"目标        {target['label']}")
    print(f"配置根      {root}")

    if not os.path.isdir(root):
        print("  [跳过] 这个宿主在本机没有配置目录；不替你新建。")
        print_manual()
        return 0

    skill_dir = args.skills_dir or target["skills"]
    print(f"技能目录    {skill_dir}")
    install_skill(skill_dir, args.force, res)

    if target["hook"] == "plugin":
        print(f"插件目录    {target['plugins']}")
        install_opencode_plugin(target, args.force, res)
    elif target["hook"] == "print-json":
        show_claude_hooks()
    else:
        print("钩子       该宿主不加载本插件支持的钩子，改为手动 inject / ingest：")
        print_manual()

    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="install_adapters.py",
        description="把 StudyLoop 装进指定的 agent（不会碰其它 agent 的目录）")
    p.add_argument("--target", default="auto",
                   choices=["auto", "opencode", "claude", "workbuddy", "generic", "none"],
                   help="装给谁；auto=按当前运行环境判断，判断不出就只打印说明")
    p.add_argument("--skills-dir", default=None, help="技能目录（generic 必填；其它宿主可覆盖）")
    p.add_argument("--force", action="store_true", help="覆盖不是本插件写的同名文件（会先备份）")
    args = p.parse_args()

    print("== 安装适配器 ==")
    res = Result()

    target_name = args.target
    if target_name == "auto":
        detected, why = detect_host()
        if detected:
            target_name = detected
            print(f"宿主        {HOSTS[detected]['label']}（依据：{why}）")
        else:
            print("宿主        判断不出（没有可识别的环境变量）")
            print("  [跳过] 为了不误写别人的目录，这次不安装任何东西。")
            print("  显式指定即可：--target opencode | claude | workbuddy | generic")
            print_manual()
            return 0

    if target_name == "none":
        print("目标        none（只看不装）")
        print_manual()
        return 0

    if target_name == "generic":
        if not args.skills_dir:
            print("[error] --target generic 需要同时给 --skills-dir", file=sys.stderr)
            return 2
        if not os.path.isdir(args.skills_dir):
            print(f"[error] 技能目录不存在：{args.skills_dir}", file=sys.stderr)
            return 2
        print(f"目标        通用（技能目录 {args.skills_dir}）")
        install_skill(args.skills_dir, args.force, res)
        print_manual()
    else:
        do_install(target_name, args, res)

    print()
    for path in res.written:
        print(f"  [写入] {path}")
    for note in res.skipped:
        print(f"  [跳过] {note}")
    for path in res.conflicts:
        print(f"  [冲突] {path}")
        print("         这个文件已存在，且不是本插件写的；没有覆盖。")
        print("         要么换个位置（--skills-dir），要么确认后加 --force（会先备份）。")

    print()
    if res.conflicts:
        print("  有冲突文件未处理，其余已写入。")
        return 3
    if res.written:
        print("  完成。只动了上面这些路径，其它 agent 的目录一个字节没碰。")
        print("  若该 agent 正在运行，重启它，钩子才会加载。")
    else:
        print("  没有写入任何文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
