#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装适配器：往**你给的目录**里装技能与钩子。代码里没有任何 agent 名字。

设计原则（v2.2.0 重写）：
    1. 不枚举宿主。装到哪里由路径决定，不由"名字"决定——任何 agent 都能用。
    2. 不给路径就只探测候选目录并打印，不写任何东西。
    3. 只在已存在的目录里写，不替你创建别人的配置根。
    4. 不认识的文件绝不覆盖：没有 @studyloop-managed 标记就报冲突（退出码 3）。
    5. --force 才覆盖，且先备份成 <文件名>.bak-<时间戳>。

用法：
    python core\\scripts\\install_adapters.py                        # 只探测，不写
    python core\\scripts\\install_adapters.py --skills-dir <目录>    # 装技能
    python core\\scripts\\install_adapters.py --skills-dir <目录> --plugin-dir <目录>
    python core\\scripts\\install_adapters.py --skills-dir <目录> --hook-json
    python core\\scripts\\install_adapters.py --discover             # 列出候选目录

目录来源（按顺序）：--skills-dir > 环境变量 STUDYLOOP_SKILLS_DIR > 自动探测（唯一候选才用）
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

BLOCK_BEGIN = "<!-- studyloop:begin -->"
BLOCK_END = "<!-- studyloop:end -->"

ENV_SKILLS = "STUDYLOOP_SKILLS_DIR"


def rules_block() -> str:
    """写进宿主指令文件的契约块：短、可执行、可撤销。"""
    mem = os.path.join(PACK, "core", "scripts", "mem.py")
    ret = os.path.join(PACK, "core", "scripts", "retrieve.py")
    pr = os.path.join(PACK, "core", "scripts", "practice.py")
    art = os.path.join(PACK, "core", "scripts", "artifacts.py")
    return "\n".join([
        BLOCK_BEGIN,
        "## StudyLoop 记忆契约",
        "",
        f"1. 会话第一条消息前：`python \"{mem}\" boot`，把输出当上下文；它会说明本轮结束要不要手动记账。",
        f"2. 回答课程内容前：`python \"{ret}\" search \"<关键词>\"`，标来源；未命中就直说没有。",
        f"3. 判分后：`python \"{pr}\" record --kp \"…\" --type … --result …`（用了提示要记 --hints）。",
        f"4. 出产物前先 `python \"{art}\" layout`，写完必须 `python \"{art}\" check <文件>`。",
        f"5. 结束一轮：按第 1 步的提示跑 `python \"{mem}\" note --text \"<一句话：问了什么、做了什么>\"`；拿不到原始对话就只写 note，不编造。",
        "6. 当前目录没有 `.study-workspace` 时，以上全部跳过，不要写入任何记忆。",
        BLOCK_END,
    ])


def upsert_rules(path: str, dry: bool, res: Result) -> None:
    block = rules_block()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            old = f.read()
        if BLOCK_BEGIN in old and BLOCK_END in old:
            head, rest = old.split(BLOCK_BEGIN, 1)
            _mid, tail = rest.split(BLOCK_END, 1)
            new = head + block + tail
        else:
            sep = "" if old.endswith("\n\n") else ("\n" if old.endswith("\n") else "\n\n")
            new = old + sep + block + "\n"
    else:
        parent = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(parent):
            res.skipped.append(f"{path}（上级目录不存在，不替你创建）")
            return
        new = block + "\n"
    if dry:
        res.written.append(path)
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    res.written.append(path)


def remove_rules(path: str, dry: bool, res: Result) -> None:
    if not os.path.exists(path):
        res.skipped.append(f"{path}（文件不存在）")
        return
    with open(path, "r", encoding="utf-8-sig") as f:
        old = f.read()
    if BLOCK_BEGIN not in old or BLOCK_END not in old:
        res.skipped.append(f"{path}（没有契约块，未改动）")
        return
    head, rest = old.split(BLOCK_BEGIN, 1)
    _mid, tail = rest.split(BLOCK_END, 1)
    new = (head.rstrip("\n") + "\n" + tail.lstrip("\n")) if head.strip() else tail.lstrip("\n")
    if dry:
        res.written.append(path + "（将删除契约块）")
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    res.written.append(path + "（已删除契约块）")


def candidates() -> list[str]:
    """扫家目录，找已经存在的 <某个目录>/skills。不预设任何 agent 名字。"""
    found: list[str] = []
    roots = [HOME, os.path.join(HOME, ".config"), os.path.join(HOME, "AppData", "Roaming")]
    seen = set()
    for root in roots:
        if not os.path.isdir(root) or root in seen:
            continue
        seen.add(root)
        try:
            names = os.listdir(root)
        except Exception:
            continue
        for n in names:
            base = os.path.join(root, n)
            if not os.path.isdir(base):
                continue
            s = os.path.join(base, "skills")
            if os.path.isdir(s):
                found.append(s)
    return sorted(set(found))


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


def put_file(path: str, content: str, mark: str, force: bool, dry: bool, res: Result) -> None:
    if os.path.exists(path):
        if not is_ours(path, mark):
            if not force:
                res.conflicts.append(path)
                return
            if dry:
                res.written.append(path + "（将覆盖，先备份）")
                return
            saved = backup(path)
            print(f"       已备份 -> {os.path.basename(saved)}")
        if dry:
            res.written.append(path)
            return
    elif dry:
        res.written.append(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    res.written.append(path)


def install_skills(skills_dir: str, force: bool, dry: bool, res: Result) -> None:
    src_root = os.path.join(PACK, "core", "skills")
    if not os.path.isdir(src_root):
        res.skipped.append(f"{src_root}（包里没有技能目录）")
        return
    for name in sorted(os.listdir(src_root)):
        src = os.path.join(src_root, name, "SKILL.md")
        if not os.path.isfile(src):
            continue
        dst_dir = os.path.join(skills_dir, name)
        with open(src, "r", encoding="utf-8") as f:
            put_file(os.path.join(dst_dir, "SKILL.md"),
                     f.read().replace("<PACK>", PACK), MARK_MD, force, dry, res)
        ref_src = os.path.join(src_root, name, "references")
        if os.path.isdir(ref_src):
            for fn in sorted(os.listdir(ref_src)):
                if not fn.lower().endswith(".md"):
                    continue
                with open(os.path.join(ref_src, fn), "r", encoding="utf-8") as f:
                    put_file(os.path.join(dst_dir, "references", fn),
                             f.read().replace("<PACK>", PACK), MARK_MD, force, dry, res)


def install_plugin(plugin_dir: str, force: bool, dry: bool, res: Result) -> None:
    src = os.path.join(PACK, "adapters", "opencode", "memory.ts")
    if not os.path.isfile(src):
        res.skipped.append(f"{src}（包里没有钩子实现）")
        return
    with open(src, "r", encoding="utf-8") as f:
        code = f.read().replace("__PACK_ROOT__", PACK.replace("\\", "/"))
    put_file(os.path.join(plugin_dir, "memory.ts"), code, MARK_TS, force, dry, res)


def show_hook_json() -> None:
    src = os.path.join(PACK, "adapters", "claude-code", "hooks.json")
    if not os.path.isfile(src):
        return
    with open(src, "r", encoding="utf-8") as f:
        text = f.read().replace("__PACK_ROOT__", PACK.replace("\\", "\\\\"))
    print()
    print("  如果你的宿主用 settings.json 的 hooks 字段，把下面这段合并进去：")
    print()
    for line in text.splitlines():
        print("    " + line)
    print()


def print_manual(skills_dir: str | None) -> None:
    mem = os.path.join(PACK, "core", "scripts", "mem.py")
    print()
    print("  手动用法（宿主没有钩子、也没有 MCP 时）：")
    print(f"    开课  python \"{mem}\" boot")
    print(f"    结束  python \"{mem}\" note --text \"<一句话总结>\"")
    print(f"    补录  python \"{mem}\" ingest --file <对话记录文件>")
    print("  其余命令（检索、判分、出题）在任何能跑命令的宿主里都一样。")
    print()
    print("  支持 MCP 的宿主，可以直接把服务端挂上去（无需按宿主写代码）：")
    print('    {"mcpServers":{"studyloop":{"command":"python",')
    print(f'      "args":["{os.path.join(PACK, "core", "scripts", "mcp_server.py")}"]}}}}')
    if skills_dir:
        print(f"  技能目录：{skills_dir}")


def pick_skills_dir(arg: str | None) -> tuple[str, str]:
    """返回 (目录, 来源说明)。找不到返回 ("", 说明)。"""
    if arg:
        return os.path.abspath(arg), "--skills-dir"
    env = os.environ.get(ENV_SKILLS)
    if env:
        return os.path.abspath(env), f"环境变量 {ENV_SKILLS}"
    found = candidates()
    if len(found) == 1:
        return found[0], "自动探测（唯一候选）"
    return "", ""


def main() -> int:
    p = argparse.ArgumentParser(
        prog="install_adapters.py",
        description="把 StudyLoop 装进你指定的技能目录；不认 agent 名字，只认路径。")
    p.add_argument("--skills-dir", default=None, help="技能安装目录（任意宿主的目录都行）")
    p.add_argument("--plugin-dir", default=None, help="可选：把钩子文件放进这个目录（宿主从目录加载插件时用）")
    p.add_argument("--rules-file", default=None, help="可选：把会话契约写进宿主的指令文件（AGENTS.md 等）")
    p.add_argument("--remove-rules", action="store_true", help="从指令文件里删除契约块")
    p.add_argument("--hook-json", action="store_true", help="可选：打印 settings.json 风格的钩子片段")
    p.add_argument("--discover", action="store_true", help="只列出本机候选技能目录，不安装")
    p.add_argument("--force", action="store_true", help="覆盖不是本插件写的同名文件（会先备份）")
    p.add_argument("--dry-run", action="store_true", help="只说会写哪些文件，不落地")
    args = p.parse_args()

    print("== 安装适配器 ==")

    if args.discover:
        found = candidates()
        print("候选技能目录（已存在 <目录>/skills 的位置）：")
        for d in found:
            print(f"  {d}")
        if not found:
            print("  （没找到；用 --skills-dir 指定你宿主读技能的位置）")
        return 0

    if args.remove_rules and not args.rules_file:
        print("[error] --remove-rules 需要同时给 --rules-file", file=sys.stderr)
        return 2

    res = Result()
    touched = False

    if args.rules_file:
        print(f"指令文件    {args.rules_file}")
        if args.remove_rules:
            remove_rules(args.rules_file, args.dry_run, res)
        else:
            upsert_rules(args.rules_file, args.dry_run, res)
        touched = True

    skills_dir = ""
    if args.skills_dir or os.environ.get(ENV_SKILLS) or (not args.rules_file):
        skills_dir, source = pick_skills_dir(args.skills_dir)
        if skills_dir:
            if not os.path.isdir(skills_dir):
                print(f"[error] 技能目录不存在：{skills_dir}", file=sys.stderr)
                print("        不替你创建目录（避免误把你宿主的目录结构带歪）。", file=sys.stderr)
                return 2
            print(f"技能目录    {skills_dir}（来源：{source}）")
            install_skills(skills_dir, args.force, args.dry_run, res)
            touched = True
        elif not args.rules_file:
            found = candidates()
            print("没有指定技能目录，也没有唯一候选；不写任何文件。")
            if found:
                print("本机找到多个候选，请挑一个：")
                for d in found:
                    print(f"  --skills-dir \"{d}\"")
            else:
                print("本机没找到候选。告诉你宿主的技能目录在哪，然后：")
                print("  --skills-dir <该目录>")
            print_manual(None)
            return 0

    if args.plugin_dir:
        if not os.path.isdir(args.plugin_dir):
            print(f"[error] 插件目录不存在：{args.plugin_dir}", file=sys.stderr)
            return 2
        print(f"插件目录    {args.plugin_dir}")
        install_plugin(args.plugin_dir, args.force, args.dry_run, res)
        touched = True

    if args.hook_json:
        show_hook_json()

    if not touched:
        print("没有可执行的动作。至少给 --skills-dir 或 --rules-file 之一。")
        print_manual(None)
        return 0

    print()
    for path in res.written:
        print(f"  [{'将写' if args.dry_run else '写入'}] {path}")
    for note in res.skipped:
        print(f"  [跳过] {note}")
    for path in res.conflicts:
        print(f"  [冲突] {path}")
        print("         已存在且不是本插件写的；没有覆盖。")
        print("         确认后加 --force（会先备份），或换一个 --skills-dir。")

    print()
    if res.conflicts:
        print("  有冲突文件未处理，其余已写入。")
        return 3
    if res.written:
        if args.dry_run:
            print("  --dry-run：以上是计划，未真正写入。")
        else:
            print("  完成。只动了上面这些路径。")
    else:
        print("  没有写入任何文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
