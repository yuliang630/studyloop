#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""间隔重复：指数遗忘曲线（半衰期模型）。

原理出处：Ebbinghaus 的遗忘曲线（1885）；"记忆强度以半衰期增长、在保持率跌破阈值时复习"
是间隔重复的公开经典做法，不含任何专有参数表。

模型：
    保持率 R(t) = 0.5 ** (t / S)      S = 记忆半衰期（天）
    下次复习时刻：解 R(t) = 目标保持率 target
        t_next = S * log2(1 / target)      （target=0.8 → 约 0.322·S）

评分来自作答结果（无用户自评）：
    hints > 0            → hard
    correct >= 1.0       → good
    0.5 <= correct < 1   → hard
    correct < 0.5        → again

半衰期更新（乘法模型）：
    首次：again 0.3 天 / hard 1.0 天 / good 3.0 天 / easy 5.0 天
    之后：again ×0.35 / hard ×1.4 / good ×2.0 / easy ×2.8
    上下限：0.02 ~ 365 天
"""

from __future__ import annotations

import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import paths as _paths

DAY = 86400.0
RATINGS = ("again", "hard", "good", "easy")
TARGET_RETENTION = 0.80

FIRST_HALFLIFE = {"again": 0.3, "hard": 1.0, "good": 3.0, "easy": 5.0}
GROWTH = {"again": 0.35, "hard": 1.4, "good": 2.0, "easy": 2.8}
MIN_HALFLIFE = 0.02
MAX_HALFLIFE = 365.0


def state_path() -> str:
    d = os.path.join(_paths.require_root(), "data", "state")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "reviews.json")


def load() -> dict:
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(data: dict) -> None:
    p = state_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def rating_for(correct: float, hints: int) -> str:
    if int(hints or 0) > 0:
        return "hard"
    c = float(correct)
    if c >= 0.999:
        return "good"
    if c >= 0.5:
        return "hard"
    return "again"


def next_interval_days(halflife_days: float, target: float = TARGET_RETENTION) -> float:
    """保持率跌到 target 所需的天数。"""
    target = min(max(target, 0.05), 0.99)
    return halflife_days * math.log2(1.0 / target)


def next_state(state: dict, rating: str, now: float,
               target: float = TARGET_RETENTION) -> dict:
    if rating not in RATINGS:
        rating = "good"
    has_history = bool(state.get("halflife_days"))
    if has_history:
        half = float(state.get("halflife_days", 3.0)) * GROWTH[rating]
    else:
        half = FIRST_HALFLIFE[rating]
    half = min(max(half, MIN_HALFLIFE), MAX_HALFLIFE)

    interval = next_interval_days(half, target)
    lapses = int(state.get("lapses", 0)) + (1 if rating == "again" else 0)
    reps = int(state.get("reps", 0)) + 1

    return {
        "halflife_days": round(half, 4),
        "interval_days": round(interval, 4),
        "target_retention": target,
        "reps": reps,
        "lapses": lapses,
        "last_rating": rating,
        "last_reviewed_at": now,
        "due_at": now + interval * DAY,
    }


def update_for(kp: str, correct: float, hints: int, now: float,
               target: float = TARGET_RETENTION) -> dict:
    data = load()
    st = data.get(kp, {})
    new = next_state(st, rating_for(correct, hints), now, target)
    data[kp] = new
    save(data)
    return new


def due_list(now: float, include_future_days: int = 0) -> list[dict]:
    horizon = now + include_future_days * DAY
    out = []
    for kp, st in load().items():
        due = float(st.get("due_at", 0))
        if due <= horizon:
            out.append({
                "kp": kp,
                "due_at": due,
                "overdue_days": round((now - due) / DAY, 2),
                "interval_days": st.get("interval_days"),
                "halflife_days": st.get("halflife_days"),
                "lapses": st.get("lapses", 0),
                "reps": st.get("reps", 0),
            })
    out.sort(key=lambda x: x["due_at"])
    return out
