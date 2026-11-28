# tests/ · L3 画像层测试基线

T0 产出。本目录是 `PLAN-L3.md` 中 T0 的唯一白名单范围；T0 不得修改 `core/scripts/` 下任何文件。

## 目录结构

```
tests/
  README.md            本文件
  fixtures/build.py    三套课程夹具的构造脚本（每次运行重建）
  samples/             四个 profile 样本（静态，参与基线哈希）
    S-zero/profile.md      0 字节
    S-skeleton/profile.md  仅生成标记 + 四个段标题
    S-invalid/profile.md   结构错误（缺必填段、字段类型错）
    S-valid/profile.md     恰好 1000 字符
  gen_samples.py       重新生成 samples/ 的脚本
  test_baseline.py     基线测试（含红断言与绿断言）
  HASHES.txt           基线哈希清单（CP1 用，随回执发送审查者留存）
```

## 夹具（fixtures/build.py）

| 夹具 | 内容 |
|---|---|
| F-empty | 仅 `.study-workspace` |
| F-l1 | 标记 + 3 条 L1 记录（同 `sid=fixture-session`，含 `trn_fixture_0001`）+ `state/path.json` + `messages.json` |
| F-full | F-l1 + L2 事实 + `state/reviews.json` + 无生成标记的 `profile.md` |

硬性规定（来自 `PLAN-L3.md` §3.1）：

1. 全部文件 **UTF-8 无 BOM**。
2. `messages.json` 用 `type`/`text`/`content`，且**省略 `time` 字段**——`ingest` 有 600 秒新鲜度门槛（`mem.py:378`），带真实时间戳的静态夹具会输出 `[skip] 会话陈旧`。
3. F-l1 的三条 L1 记录均 `sid=fixture-session`。
4. 每次执行（含 CP5 重放）必须新建工作副本：`note` 按 `turn_key` 去重、`ingest` 有游标，复用副本会输出 `[skip]`。

L1 记录的时间戳按运行时刻生成（相对当前时间），保证 A3 的"最近窗口"可测；因此夹具是**动态构造**，参与哈希的是 `build.py` 本身，不是生成物。

## 样本（samples/）

静态文件，参与基线哈希。S-valid 恰好 1000 字符，是 A5 与 CP1 绿断言的输入。

重新生成：`python tests/gen_samples.py`（会覆盖 samples/，须同时更新 `HASHES.txt`）。

## 基线测试

```powershell
python -m unittest discover -s tests -v
```

CP1 要求**一红一绿**：

- **红**（当前代码失败，修复后通过）：
  - `test_red_init_produces_profile` —— `init` 后应存在 `profile.md`，当前不存在。
  - `test_red_profile_build_command` —— `mem.py profile --build` 应退出 0，当前因无此子命令退出 2。
- **绿**（当前即通过，证明基线不是恒红）：
  - `test_green_valid_sample_structure` —— S-valid 恰好 1000 字符、含生成标记、四段齐全、每段至少一条列表项。
  - `test_green_sample_lengths_distinct` —— 四个样本的长度互不相同，S-zero 为 0 字节。

红断言只针对 D-1（画像无生产者），不针对任何待实现细节；绿断言只做结构自检，不依赖 T2 才产出的校验器。

## 哈希清单

`HASHES.txt` 由 `python tests/gen_hashes.py` 生成，覆盖 `samples/`、`fixtures/build.py`、`test_baseline.py`。CP1 通过时随回执发送审查者外部留存，CP5 以子集判定比对。
