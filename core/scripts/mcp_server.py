#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StudyLoop MCP 服务端（标准库实现，stdio + 换行分隔的 JSON-RPC 2.0）。

定位：**传输层薄壳**。这里不许有业务逻辑——所有能力都通过调用既有脚本完成，
否则又多一处会漂的实现。宿主怎么启动它由宿主的 mcpServers 配置决定：

    {
      "mcpServers": {
        "studyloop": {
          "command": "python",
          "args": ["<PACK>\\core\\scripts\\mcp_server.py"]
        }
      }
    }

可选环境变量：
    STUDYLOOP_COURSE   默认课程目录（不给就在每次调用时按 cwd / MEMORY_ROOT 解析）

工具：boot / note / search / record / due
资源：studyloop://profile、studyloop://due
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(SCRIPTS))

PROTOCOL_VERSION = "2024-11-05"

INSTRUCTIONS = (
    "StudyLoop 学习插件。会话开始先调用 studyloop_boot，把返回的记忆块当作上下文；"
    "一轮学习结束时调用 studyloop_note，写一句“问了什么、做了什么”的摘要（不要编造细节）。"
    "回答课程问题前先 studyloop_search 并标注来源；未命中就明说没有。"
    "判分用 studyloop_record，提示次数必须如实记录。"
    "如果这些工具不可用，改用命令行：mem.py boot / mem.py note。"
)


def version() -> str:
    try:
        with open(os.path.join(PACK, "VERSION.json"), "r", encoding="utf-8") as f:
            return str(json.load(f).get("version") or "0.0.0")
    except Exception:
        return "0.0.0"


def course_env(course: str | None) -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if course:
        env["MEMORY_ROOT"] = os.path.join(os.path.abspath(course), "记忆")
    return env


def call(script: str, args: list[str], course: str | None = None) -> tuple[int, str]:
    """调用既有脚本，返回 (退出码, 输出)。不提业务逻辑。"""
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=course_env(course))
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


TOOLS = [
    {
        "name": "studyloop_boot",
        "description": "开课注入：返回学习者画像、进度、今日待复习，以及本轮结束该不该手动记账。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course": {"type": "string", "description": "课程目录；不传则用当前目录"},
                "chars": {"type": "integer", "description": "注入块最大字符数，默认 1500"},
            },
        },
    },
    {
        "name": "studyloop_note",
        "description": "本轮记账：写一句摘要进 L1（来源标 agent-note，按内容去重）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "一句话：问了什么、做了什么、结果如何"},
                "sid": {"type": "string", "description": "会话标识，可选"},
                "course": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "studyloop_search",
        "description": "在课程素材里做关键词检索，返回带来源路径的片段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top": {"type": "integer", "description": "返回条数，默认 3"},
                "course": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "studyloop_record",
        "description": "记录一次作答并判定掌握度；用了提示要如实填 hints。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kp": {"type": "string", "description": "知识点"},
                "type": {"type": "string", "enum": ["memory", "procedure", "concept", "design"]},
                "result": {"type": "number", "description": "1 对 / 0.5 部分对 / 0 错"},
                "hints": {"type": "integer"},
                "course": {"type": "string"},
            },
            "required": ["kp", "type", "result"],
        },
    },
    {
        "name": "studyloop_due",
        "description": "列出今天该复习的知识点。",
        "inputSchema": {"type": "object", "properties": {"course": {"type": "string"}}},
    },
]

RESOURCES = [
    {"uri": "studyloop://profile", "name": "learner profile", "mimeType": "text/markdown",
     "description": "学习者画像（L3 profile.md）"},
    {"uri": "studyloop://due", "name": "due reviews", "mimeType": "text/plain",
     "description": "今日待复习清单"},
]


def tool_call(name: str, args: dict) -> str:
    course = args.get("course")
    if name == "studyloop_boot":
        chars = str(int(args.get("chars") or 1500))
        return call("mem.py", ["boot", "--transport", "mcp", "--chars", chars], course)[1]
    if name == "studyloop_note":
        cmd = ["note", "--text", str(args.get("text", ""))]
        if args.get("sid"):
            cmd += ["--sid", str(args["sid"])]
        return call("mem.py", cmd, course)[1]
    if name == "studyloop_search":
        top = str(int(args.get("top") or 3))
        return call("retrieve.py", ["search", str(args.get("query", "")), "--top", top], course)[1]
    if name == "studyloop_record":
        cmd = ["record", "--kp", str(args.get("kp", "")), "--type", str(args.get("type", "memory")),
               "--result", str(args.get("result", 0))]
        if args.get("hints") is not None:
            cmd += ["--hints", str(int(args["hints"]))]
        return call("practice.py", cmd, course)[1]
    if name == "studyloop_due":
        return call("review.py", ["due"], course)[1]
    raise KeyError(name)


def resource_read(uri: str) -> str:
    if uri == "studyloop://profile":
        root = os.environ.get("MEMORY_ROOT")
        if not root:
            sys.path.insert(0, SCRIPTS)
            import paths as _paths  # noqa: PLC0415
            resolved = _paths.try_resolve_root()
            root = os.path.join(resolved, "") if resolved else ""
        path = os.path.join(root, "data", "L3", "default", "profile.md") if root else ""
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        return "（还没有画像：先跑 mem.py init，再积累学习记录）"
    if uri == "studyloop://due":
        return call("review.py", ["due"])[1]
    raise KeyError(uri)


def respond(msg_id, result=None, error=None) -> dict:
    out: dict = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    return out


def handle(req: dict) -> dict | None:
    method = req.get("method") or ""
    msg_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return respond(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "studyloop", "version": version()},
            "instructions": INSTRUCTIONS,
        })
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return respond(msg_id, {})
    if method == "tools/list":
        return respond(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        try:
            text = tool_call(str(name), params.get("arguments") or {})
        except Exception as exc:
            return respond(msg_id, error={"code": -32603, "message": f"{type(exc).__name__}: {exc}"})
        return respond(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
    if method == "resources/list":
        return respond(msg_id, {"resources": RESOURCES})
    if method == "resources/read":
        uri = str(params.get("uri") or "")
        try:
            text = resource_read(uri)
        except Exception as exc:
            return respond(msg_id, error={"code": -32602, "message": f"{type(exc).__name__}: {exc}"})
        return respond(msg_id, {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]})

    return respond(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            print(json.dumps(respond(None, error={"code": -32700, "message": f"parse error: {exc}"}),
                             ensure_ascii=False), flush=True)
            continue
        if not isinstance(req, dict):
            continue
        resp = handle(req)
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
