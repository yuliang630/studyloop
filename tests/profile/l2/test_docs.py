# -*- coding: utf-8 -*-
"""A24：L2 不进注入块，文档须写明"需主动查询"且与实现一致。"""

from __future__ import annotations

import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def read(rel):
    with open(os.path.join(PACK, rel), encoding="utf-8") as f:
        return f.read()


class L2Scope(unittest.TestCase):
    def test_tech_states_l2_not_injected(self):
        tech = read("TECH.md")
        self.assertIn("L2 facts are not injected", tech)
        self.assertIn("fact-list", tech)

    def test_readme_states_l2_not_injected(self):
        readme = read("README.md")
        self.assertIn("L2 事实**不自动注入**", readme)
        self.assertIn("fact-list", readme)

    def test_implementation_matches_docs(self):
        """注入块只拼 profile / recent / progress，不含 L2。"""
        mem = read(os.path.join("core", "scripts", "mem.py"))
        block = mem.split("def build_inject_block", 1)[1].split("def ", 1)[0]
        self.assertIn("profile", block)
        self.assertIn("recent", block)
        self.assertIn("progress", block)
        self.assertNotIn("L2", block.split("return", 1)[0].replace("L2 事实", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
