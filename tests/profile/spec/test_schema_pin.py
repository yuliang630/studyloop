# -*- coding: utf-8 -*-
"""A18 第三腿：把冻结 schema 与实现钉在一起。

没有这条测试时，"schema 冻结物"与"实现"之间没有任何可执行的连接——
recent 预算从 215 改成别的、模板开销从 85 改成别的，测试都不会红。
这里把两份东西都写成字面量：

  1. `PLAN-L3-schema.md` 的 sha256（附录 G 的冻结值）；
  2. `profile_spec` 的六个常量。

改 schema 或改常量都必须同步改本文件，否则红——这份冗余是刻意的。
"""

from __future__ import annotations

import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(PACK, "core", "scripts"))

import profile_spec  # noqa: E402

# 附录 G 记录的冻结哈希；改 schema 必须同步更新这里
SCHEMA_SHA256 = "69d4d91d5a2cda20b5a2e1e010c4e775b975863e1a7fe850fa3a270517cadb19"


class SchemaPin(unittest.TestCase):
    def test_schema_file_hash(self):
        path = os.path.join(PACK, "PLAN-L3-schema.md")
        with open(path, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(SCHEMA_SHA256, actual,
                         "schema 已变更：请同步更新附录 G 与本处的冻结哈希")

    def test_budget_constants(self):
        self.assertEqual(
            {"profile": 1000, "recent": 215, "progress": 200, "total": 1500},
            profile_spec.LIMITS)
        self.assertEqual(85, profile_spec.TEMPLATE_OVERHEAD)

    def test_shape_constants(self):
        self.assertEqual({"goal": 8, "mastery": 8, "weak": 5}, profile_spec.COUNTS)
        self.assertEqual(18, profile_spec.NAME_MAX)
        self.assertEqual(8, profile_spec.ID_MAX)
        self.assertEqual(4, profile_spec.RECENT_MAX_ITEMS)

    def test_paragraph_order(self):
        """段序即裁剪优先级，schema §1 与实现必须一致。"""
        self.assertEqual(
            ("### 目标与进度", "### 掌握度概览", "### 薄弱环节", "### 学习节奏"),
            tuple(profile_spec.PARAS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
