# -*- coding: utf-8 -*-
"""T4b：钩子层不再硬编码 L3/default，按 RECALLOOP_SCOPE 解析（A23）。

**静态检查，未运行**：`memory.ts` 是 OpenCode 插件模块，依赖宿主的 plugin API
与工作区绑定，不是一个可独立执行的脚本；本测试只做源码级断言。运行验证留给
适配器的集成测试（不在本项目范围，见 §2.2 的 N4）。
"""

from __future__ import annotations

import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(HERE))


class AdapterScope(unittest.TestCase):
    def setUp(self):
        path = os.path.join(PACK, "adapters", "opencode", "memory.ts")
        with open(path, encoding="utf-8") as f:
            self.src = f.read()

    def test_no_hardcoded_default_scope(self):
        self.assertNotIn("L3/default/", self.src, "钩子层仍硬编码 L3/default")

    def test_reads_scope_env(self):
        self.assertIn("RECALLOOP_SCOPE", self.src)

    def test_cache_paths_use_scope_variable(self):
        self.assertIn("data/L3/${scope}/profile.md", self.src)
        self.assertIn("data/L3/${scope}/recent.md", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
