#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""检索：教材切块 + BM25 + 增量索引 + 评测。纯标准库。

为什么不用 jieba / numpy / faiss：
    插件套件的依赖只有 Python 本身。分词用"中文二元组 + 英文按词"的朴素方案，
    对教材类文本够用；检索质量靠 eval 量化，不靠感觉。

命令：
    python retrieve.py index  [--root .]          重建索引
    python retrieve.py sync   [--root .]          按指纹增量更新
    python retrieve.py search "链式法则" [--top 3] [--json]
    python retrieve.py eval --dataset qa.jsonl [--k 5]
    python retrieve.py stats

索引位置：<工作区>\记忆\data\state\index.json
素材范围：教材\ 资料\ 笔记\
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as _paths  # noqa: E402
import parsers as _parsers  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SOURCE_DIRS = ["教材", "资料", "笔记"]
TEXT_EXT = _parsers.ALL_EXT   # 解析层登记了什么就收什么；读不了的会在跳过清单里报原因
PDF_EXT = _parsers.PDF_EXT
MAX_DOC_CHARS = 200000


def source_dirs(root: str) -> list[str]:
    """课程可在 .study-workspace 里自定义素材目录，例如 ["课程","archive/教程"]。"""
    marker = os.path.join(root, ".study-workspace")
    try:
        with open(marker, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        dirs = cfg.get("sources")
        if isinstance(dirs, list) and dirs:
            return [str(d) for d in dirs]
    except Exception:
        pass
    return SOURCE_DIRS
CHUNK_MAX = 600
CHUNK_MIN = 120
K1, B = 1.5, 0.75

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
WORD = re.compile(r"[a-z0-9]+")


def state_dir() -> str:
    d = os.path.join(_paths.require_root(), "data", "state")
    os.makedirs(d, exist_ok=True)
    return d


def index_path() -> str:
    return os.path.join(state_dir(), "index.json")


# ---------------------------------------------------------------- 分词


def tokenize(text: str) -> list[str]:
    """中文按二元组、英文数字按词。无第三方依赖。"""
    low = text.lower()
    tokens: list[str] = []
    for run in CJK.findall(low):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    tokens.extend(WORD.findall(low))
    return tokens


# ---------------------------------------------------------------- 读文件与切块


def read_document(path: str) -> tuple[str, str]:
    """返回 (文本, 说明)。解析引擎由 parsers.py 按本机能力选择。"""
    res = _parsers.read(path, MAX_DOC_CHARS)
    if "error" in res:
        return "", res["error"]
    note = res.get("engine", "")
    if res.get("note"):
        note = f"{note}; {res['note']}"
    return res.get("text", ""), note


def chunk_text(text: str) -> list[str]:
    """按空行切段，过短的合并，过长的再切。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
        elif len(buf) + len(p) + 2 <= CHUNK_MAX:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            buf = p
        while len(buf) > CHUNK_MAX:
            chunks.append(buf[:CHUNK_MAX])
            buf = buf[CHUNK_MAX:]
    if buf:
        if chunks and len(buf) < CHUNK_MIN:
            chunks[-1] = chunks[-1] + "\n\n" + buf
        else:
            chunks.append(buf)
    return chunks


def collect_files(root: str) -> list[dict]:
    out = []
    for d in source_dirs(root):
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in _parsers.ALL_EXT:
                    continue
                full = os.path.join(dirpath, name)
                st = os.stat(full)
                out.append({
                    "path": os.path.relpath(full, root).replace("\\", "/"),
                    "abs": full,
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                })
    return out


# ---------------------------------------------------------------- 建/增量


def build_for_file(meta: dict, root: str) -> tuple[list[dict], str]:
    text, note = read_document(meta["abs"])
    if not text.strip():
        return [], note or "无文本"
    chunks = []
    for pos, piece in enumerate(chunk_text(text)):
        toks = tokenize(piece)
        if not toks:
            continue
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        chunks.append({
            "path": meta["path"], "pos": pos, "len": len(toks),
            "text": piece[:CHUNK_MAX], "tf": tf,
        })
    return chunks, note


def finalize(chunks: list[dict]) -> dict:
    df: dict[str, int] = {}
    for c in chunks:
        for t in c["tf"]:
            df[t] = df.get(t, 0) + 1
    avgdl = sum(c["len"] for c in chunks) / len(chunks) if chunks else 0.0
    return {"v": 1, "chunks": chunks, "df": df, "n": len(chunks), "avgdl": avgdl}


def load_index() -> dict:
    p = index_path()
    if not os.path.exists(p):
        return {"v": 1, "chunks": [], "df": {}, "n": 0, "avgdl": 0.0, "files": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"v": 1, "chunks": [], "df": {}, "n": 0, "avgdl": 0.0, "files": {}}


def save_index(idx: dict) -> None:
    p = index_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    os.replace(tmp, p)


def _report_skipped(skipped: list[tuple[str, str]]) -> None:
    if not skipped:
        return
    print(f"[warn] 跳过 {len(skipped)} 个文件（内容未进索引）：")
    for path, reason in skipped[:10]:
        print(f"       - {path}  →  {reason}")
    if len(skipped) > 10:
        print(f"       …另有 {len(skipped) - 10} 个")


def cmd_index(args) -> int:
    root = os.path.abspath(args.root)
    metas = collect_files(root)
    chunks: list[dict] = []
    skipped: list[tuple[str, str]] = []
    engines: dict[str, int] = {}
    for m in metas:
        got, note = build_for_file(m, root)
        chunks.extend(got)
        if not got:
            skipped.append((m["path"], note))
        else:
            engines[note.split("(")[0] or "builtin"] = engines.get(note.split("(")[0] or "builtin", 0) + 1
    idx = finalize(chunks)
    idx["files"] = {m["path"]: {"size": m["size"], "mtime": m["mtime"]} for m in metas}
    save_index(idx)
    print(f"[ok] 索引已重建：{len(metas)} 个文件 / {idx['n']} 个片段")
    if engines:
        print("     解析引擎：" + "，".join(f"{k}×{v}" for k, v in sorted(engines.items())))
    print(f"     {index_path()}")
    _report_skipped(skipped)
    return 0


def cmd_sync(args) -> int:
    root = os.path.abspath(args.root)
    idx = load_index()
    old_files: dict = idx.get("files", {})
    metas = collect_files(root)
    new_files = {m["path"]: {"size": m["size"], "mtime": m["mtime"]} for m in metas}

    changed = {p for p, v in new_files.items() if old_files.get(p) != v}
    removed = {p for p in old_files if p not in new_files}

    if not changed and not removed:
        print(f"[ok] 素材未变，索引保持原样（{idx['n']} 个片段）")
        return 0

    kept = [c for c in idx.get("chunks", []) if c["path"] not in changed and c["path"] not in removed]
    added: list[dict] = []
    skipped: list[tuple[str, str]] = []
    engines: dict[str, int] = {}
    by_path = {m["path"]: m for m in metas}
    for p in sorted(changed):
        got, note = build_for_file(by_path[p], root)
        added.extend(got)
        if not got:
            skipped.append((p, note))
        else:
            key = note.split("(")[0] or "builtin"
            engines[key] = engines.get(key, 0) + 1

    new_idx = finalize(kept + added)
    new_idx["files"] = new_files
    save_index(new_idx)
    print(f"[ok] 增量更新：新增/变更 {len(changed)}，移除 {len(removed)}，"
          f"片段 {idx['n']} → {new_idx['n']}")
    if engines:
        print("     解析引擎：" + "，".join(f"{k}×{v}" for k, v in sorted(engines.items())))
    _report_skipped(skipped)
    return 0


# ---------------------------------------------------------------- 查询


def search(idx: dict, query: str, top: int = 3) -> list[dict]:
    q_tokens = tokenize(query)
    if not q_tokens or not idx.get("chunks"):
        return []
    n = idx["n"] or 1
    avgdl = idx["avgdl"] or 1.0
    df = idx["df"]
    scored = []
    for c in idx["chunks"]:
        s = 0.0
        for t in q_tokens:
            f = c["tf"].get(t, 0)
            if not f:
                continue
            d = df.get(t, 0)
            idf = math.log(1 + (n - d + 0.5) / (d + 0.5))
            denom = f + K1 * (1 - B + B * c["len"] / avgdl)
            s += idf * (f * (K1 + 1)) / denom if denom else 0.0
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, c in scored[:top]:
        out.append({
            "path": c["path"], "pos": c["pos"],
            "score": round(score, 3), "text": c["text"],
        })
    return out


def cmd_search(args) -> int:
    idx = load_index()
    if not idx.get("chunks"):
        print("[warn] 索引为空，先跑：python retrieve.py index")
        return 1
    hits = search(idx, args.query, args.top)
    if args.json:
        print(json.dumps({"query": args.query, "hits": hits}, ensure_ascii=False))
        return 0
    if not hits:
        print(f"（未命中：{args.query}）")
        return 0
    for h in hits:
        print(f"--- {h['path']} #{h['pos']}  score={h['score']}")
        print(h["text"][:300].replace("\n", " "))
        print()
    return 0


# ---------------------------------------------------------------- 评测


def cmd_eval(args) -> int:
    idx = load_index()
    if not idx.get("chunks"):
        print("[warn] 索引为空")
        return 1
    cases = []
    with open(args.dataset, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    if not cases:
        print("[warn] 数据集为空")
        return 1

    k = args.k
    recalls, rrs = [], []
    for case in cases:
        q = case["query"]
        gold = [g for g in case.get("gold", []) if g]
        hits = search(idx, q, k)
        joined = [h["text"] for h in hits]
        found = 0
        first_rank = None
        for gi, g in enumerate(gold):
            for rank, text in enumerate(joined, start=1):
                if g in text:
                    found += 1
                    if first_rank is None or rank < first_rank:
                        first_rank = rank
                    break
        recalls.append(found / len(gold) if gold else 0.0)
        rrs.append(1.0 / first_rank if first_rank else 0.0)
        if args.verbose:
            print(f"  {q} → 命中 {found}/{len(gold)}  top={len(hits)}")

    mean_recall = sum(recalls) / len(recalls)
    mrr = sum(rrs) / len(rrs)
    print(f"用例 {len(cases)}  k={k}")
    print(f"Recall@{k} = {mean_recall:.3f}")
    print(f"MRR       = {mrr:.3f}")
    ok = mean_recall >= args.min_recall
    print(f"阈值 {args.min_recall} → {'通过' if ok else '未通过'}")
    return 0 if ok else 1


def cmd_stats(args) -> int:
    idx = load_index()
    files = idx.get("files", {})
    print(f"索引文件 {index_path()}")
    print(f"素材 {len(files)} 个 / 片段 {idx.get('n', 0)} 个")
    print(f"词表 {len(idx.get('df', {}))} 个 token")
    return 0


def cmd_add(args) -> int:
    """把素材复制进课程目录（默认 教材\\），随后增量同步。"""
    root = os.getcwd()
    to = args.to or "教材"
    dst_dir = os.path.join(root, to)
    os.makedirs(dst_dir, exist_ok=True)

    copied = []
    skipped = []
    for path in args.paths:
        full = os.path.abspath(path)
        if os.path.isdir(full):
            for dp, _dirs, files in os.walk(full):
                for n in files:
                    if os.path.splitext(n)[1].lower() in _parsers.ALL_EXT:
                        copied.append((os.path.join(dp, n), n))
        elif os.path.isfile(full):
            copied.append((full, os.path.basename(full)))
        else:
            skipped.append((path, "路径不存在"))

    done = 0
    for source, name in copied:
        target = os.path.join(dst_dir, name)
        if os.path.exists(target):
            skipped.append((source, "目标已存在，跳过"))
            continue
        try:
            shutil.copy2(source, target)
            done += 1
        except Exception as exc:
            skipped.append((source, "复制失败: %s" % exc))

    print("[ok] 已放入 %d 个文件 -> %s/" % (done, to))
    for source, reason in skipped[:10]:
        print("       - %s  ->  %s" % (source, reason))
    if done == 0 and not skipped:
        print("       （没有可解析的素材类型）")
    return cmd_sync(argparse.Namespace(root=root))


def main() -> int:
    p = argparse.ArgumentParser(prog="retrieve.py", description="教材检索（BM25，零依赖）")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("index", "sync"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", default=os.getcwd())

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--top", type=int, default=3)
    s.add_argument("--json", action="store_true")

    e = sub.add_parser("eval")
    e.add_argument("--dataset", required=True)
    e.add_argument("--k", type=int, default=5)
    e.add_argument("--min-recall", type=float, default=0.6)
    e.add_argument("--verbose", action="store_true")

    sub.add_parser("stats")

    a = sub.add_parser("add", help="把素材放进课程目录并同步索引")
    a.add_argument("paths", nargs="+")
    a.add_argument("--to", default="教材", help="目标子目录，默认 教材")

    args = p.parse_args()
    if args.cmd == "index":
        return cmd_index(args)
    if args.cmd == "sync":
        return cmd_sync(args)
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "eval":
        return cmd_eval(args)
    if args.cmd == "stats":
        return cmd_stats(args)
    if args.cmd == "add":
        return cmd_add(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
