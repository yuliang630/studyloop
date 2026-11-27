#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""掌握判定：贝叶斯知识追踪（BKT）。

模型出处：Corbett, A. T., & Anderson, J. R. (1995). Knowledge tracing: Modeling
the acquisition of procedural knowledge. User Modeling and User-Adapted
Interaction, 4(4), 253–278. 公开的经典教育测量模型，纯数学。

四个参数：
    p_l0  初始已掌握的先验概率（默认 0.30）
    p_t   每次练习从"不会"迁移到"会"的概率（默认 0.15）
    p_g   不会但猜对的概率（默认 0.20）
    p_s   会但失误答错的概率（默认 0.10）

一次更新的两步：
    1) 观测更新（贝叶斯）：
       答对：p' = p(1-p_s) / [p(1-p_s) + (1-p)p_g]
       答错：p' = p·p_s   / [p·p_s   + (1-p)(1-p_g)]
    2) 学习迁移：
       p'' = p' + (1-p')·p_t

门槛：定量类知识点要求事后概率 ≥ 0.95；概念/设计类仍走定性判定（这不是算法，是教学规则）。

为什么不再用"加权准确率 + 置信封顶"：
    那套规则需要人为设定"答几题才可信"，本质是拍脑袋的补丁。
    BKT 用概率自然表达不确定性：同样答对两次，先验低时后验也不会高。
"""

from __future__ import annotations

# 文献默认值；P_G / P_S 后续可用真实作答标定
P_L0 = 0.30
P_T = 0.15
P_G = 0.20
P_S = 0.10

# 定量类的门槛（事后概率）
GATE = 0.95

QUALITATIVE_TYPES = frozenset({"concept", "design"})
QUALITATIVE_PASS_DISPLAY = 1.0


def bkt_state(correctness: list[bool | float], p_l0: float = P_L0,
              p_t: float = P_T, p_g: float = P_G, p_s: float = P_S) -> dict:
    """跑完整条作答序列，返回末尾状态与逐步轨迹。

    允许 0..1 的部分得分：把 c 当作"答对的概率"做加权观测更新
    （c=1 纯答对，c=0 纯答错，c=0.5 视为一半证据）。
    """
    p = float(p_l0)
    trace = []
    for raw in correctness:
        c = max(0.0, min(1.0, float(raw)))
        p_correct = p * (1 - p_s) + (1 - p) * p_g
        p_correct = min(max(p_correct, 1e-9), 1 - 1e-9)
        p_given_correct = p * (1 - p_s) / p_correct
        p_given_wrong = p * p_s / (1 - p_correct)
        # 部分得分在两个后验之间线性插值
        p_post = c * p_given_correct + (1 - c) * p_given_wrong
        p_learn = p_post + (1 - p_post) * p_t
        trace.append({"obs": c, "posterior": round(p_post, 4), "after_learn": round(p_learn, 4)})
        p = p_learn
    return {"p_mastery": p, "trace": trace}


def compute_mastery(correctness: list[bool | float]) -> float:
    """按时间顺序的作答结果 → 掌握概率 0..1。"""
    if not correctness:
        return 0.0
    return bkt_state(list(correctness))["p_mastery"]


def gate_threshold(kp_type: str) -> float:
    t = (kp_type or "").lower()
    if t in QUALITATIVE_TYPES:
        return QUALITATIVE_PASS_DISPLAY
    return GATE


def is_mastered(kp_type: str, mastery: float = 0.0,
                qualitative_pass: bool = False, visuals_ok: bool = True) -> bool:
    if not visuals_ok:
        return False
    t = (kp_type or "").lower()
    if t in QUALITATIVE_TYPES:
        return bool(qualitative_pass)
    return float(mastery) >= gate_threshold(t)


def next_action(kp_type: str, mastery: float, qualitative_pass: bool = False,
                visuals_ok: bool = True) -> dict:
    passed = is_mastered(kp_type, mastery, qualitative_pass, visuals_ok)
    threshold = gate_threshold(kp_type)
    if passed:
        return {
            "action": "advance", "passed": True,
            "mastery": round(float(mastery), 3), "threshold": threshold,
            "reason": "已达门槛，可进入下一个知识点（跳过重复讲解）",
        }
    if not visuals_ok:
        reason = "要求的视觉任务未通过或使用了提示，不算证据"
    elif (kp_type or "").lower() in QUALITATIVE_TYPES:
        reason = "概念/设计类需定性通过（能讲清楚），概率再高也不放行"
    else:
        reason = f"已掌握概率 {round(float(mastery), 3)} 未达 {threshold}（BKT 后验）"
    return {
        "action": "practice", "passed": False,
        "mastery": round(float(mastery), 3), "threshold": threshold,
        "reason": reason,
    }


# ---------------------------------------------------------------- CLI


def _parse_scores(text: str) -> list[float]:
    out: list[float] = []
    for piece in text.replace(" ", "").split(","):
        if not piece:
            continue
        v = piece.lower()
        if v in {"1", "true", "t", "y", "yes", "对", "正确"}:
            out.append(1.0)
        elif v in {"0", "false", "f", "n", "no", "错", "错误"}:
            out.append(0.0)
        else:
            out.append(max(0.0, min(1.0, float(v))))
    return out


def main() -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(prog="mastery.py", description="掌握判定（BKT）")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compute", help="按作答序列计算已掌握概率")
    c.add_argument("--scores", required=True, help="逗号分隔，如 1,1,0 或 0.5,1")
    c.add_argument("--json", action="store_true")

    g = sub.add_parser("gate", help="判断是否过门槛")
    g.add_argument("--type", required=True, help="memory/procedure/concept/design")
    g.add_argument("--mastery", type=float, default=0.0)
    g.add_argument("--qualitative", action="store_true")
    g.add_argument("--visuals-failed", action="store_true")
    g.add_argument("--json", action="store_true")

    args = p.parse_args()

    if args.cmd == "compute":
        seq = _parse_scores(args.scores)
        state = bkt_state(seq) if seq else {"p_mastery": 0.0, "trace": []}
        if args.json:
            print(json.dumps({
                "attempts": len(seq),
                "mastery": round(state["p_mastery"], 4),
                "params": {"p_l0": P_L0, "p_t": P_T, "p_g": P_G, "p_s": P_S},
                "trace": state["trace"],
            }, ensure_ascii=False))
        else:
            print(f"作答 {len(seq)} 次 → 已掌握概率 {state['p_mastery']:.4f}")
            for i, t in enumerate(state["trace"], 1):
                print(f"  第 {i} 次 obs={t['obs']} → 后验 {t['posterior']} → 学习后 {t['after_learn']}")
        return 0

    res = next_action(args.type, args.mastery, args.qualitative, not args.visuals_failed)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"[{res['action']}] 概率={res['mastery']} 门槛={res['threshold']}")
        print(f"  {res['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
