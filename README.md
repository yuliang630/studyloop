# Recalloop · 忆环

**中文** ｜ [English](#english)

给 AI agent 用的学习插件：**记住你**（记忆）、**判你过没过**（掌握度）、**答之前先查教材**（检索并标来源）、**该复习时提醒你**（遗忘曲线排期），还能按模板出**试卷 / 教案 / 讲义 / 课程规划**。

名字来自两件事：**recall**（把学过的调出来）+ **loop**（循环）。中文「忆环」是逐字对应：忆 = recall，环 = loop。查到判、判到练、练到复习、复习到出题，转一圈再回到下一个知识点。

没有界面，不捆运行时，必需依赖只有 Python 3.11+。

当前版本 **0.1.0**（首个公开测试版），MIT 许可。

---

## 它解决什么

普通的 AI 对话每轮都是失忆的：你说"上次那个知识点"，它不知道你在说什么；你学完一章，它不知道你过没过。

这个插件把四件事接到对话循环上：

1. **记忆**——每轮自动写进课程目录，下一轮自动注入画像，换会话也记得
2. **判定**——用贝叶斯知识追踪（BKT）算"已掌握概率"，门槛 0.95；概念和设计类必须自己讲清楚才算过；用了提示的那次作答不计入证据
3. **检索**——回答教材问题前先查原文并标来源，查不到就直说
4. **推进**——按知识点路径给"下一课"，按遗忘曲线（半衰期）排复习

## 它不做什么

- 没有界面、没有多用户、没有云同步
- 不做语义检索（只有关键词 BM25）
- 不捆绑 Python 或 Node，环境自己装
- **不在课程目录之外写任何东西**
- **不替你建课**：课程文件夹和标记文件由你（或你的 agent）创建

---

## 环境与依赖

| 项 | 要求 |
|---|---|
| 系统 | Windows（当前版本） |
| Python | **3.11 或更高** |
| 第三方库 | **必需的一个都没有**（只用标准库） |
| 可选 | 任何你机器上已经有的解析/OCR 引擎，见下文「支持的格式」 |

只有裸 Python 也能用：md / txt / html / ipynb / epub 全部可读。可选引擎只是扩大能读的格式范围，缺了不影响其余功能。

---

## 安装

### 方式一：自动

```powershell
双击 install.bat
```

它会检查 Python 版本、写可选配置，然后**探测本机已有的技能目录**：只有一个就用它，有多个就列出来让你挑，一个都没有就打印手动用法。装完重启 agent。

### 方式二：手动三步

```powershell
# 1. 写可选的本机偏好（不记录任何本机绝对路径）
python core\scripts\setup_config.py

# 2. 把技能装进你宿主的技能目录（换成你 agent 读技能的那个目录）
python core\scripts\install_adapters.py --skills-dir "%USERPROFILE%\.your-agent\skills"

# 3. 自检
python core\scripts\probe.py
```

**安装器里没有任何 agent 名字。** 装到哪里完全由目录决定，所以任何 agent 都能装 —— 包括我没听说过的。

不知道目录在哪，先让它扫：

```powershell
python core\scripts\install_adapters.py --discover
```

它会列出本机**实际存在**的 `<某目录>/skills`。家目录里有多套时它不猜，只把每个候选列成一条 `--skills-dir` 命令。

可选项：

| 参数 | 用途 |
|---|---|
| `--plugin-dir <目录>` | 宿主从某个目录加载插件时，把钩子文件放进去 |
| `--hook-json` | 宿主用 `settings.json` 的 `hooks` 字段时，打印片段供你合并 |
| `--dry-run` | 只说要写哪些文件，不落地 |
| `--force` | 覆盖不是本插件写的同名文件（先备份） |

五条硬规矩：

| 规矩 | 表现 |
|---|---|
| 不认名字，只认目录 | 代码里没有 agent 白名单；路径给对就能装 |
| 不给目录就不写 | 没有 `--skills-dir`、没有环境变量、候选也不唯一 → 只打印，退出 0 |
| 不创建目录 | 目标目录不存在 → 报错退出 2，不替你造目录 |
| 不覆盖别人的文件 | 没有 `@recalloop-managed` 标记 → 冲突，退出 3，原文件不动 |
| 覆盖先备份 | `--force` 才写，先存 `<文件名>.bak-<时间戳>` |

环境变量也能给目录（适合批量/脚本）：`RECALLOOP_SKILLS_DIR`（老名字 `STUDYLOOP_SKILLS_DIR` 仍然认）。

**从更早的预发布版本升级**：那些文件没有归属标记，第一次会被判为"别人的文件"并报冲突（退出码 3）。确认那些文件确实是本插件以前装的，加一次 `--force` 即可，旧文件会先备份成 `.bak-<时间戳>`。

**装完重启 agent**，钩子才会加载（技能不需要重启，新会话读一次即可）。

### 关于 config.json

这个包**可以放在任何目录**，脚本根据自身位置定位包根，所以 `config.json` 里不记录本机路径。它只保存一个可选项：

```json
{ "v": 1, "default_workspace": "" }
```

`default_workspace` 是"不在课程目录里时默认用哪个课程"，可以不设。设了也只是显式指定，不会变成偷偷写数据的兜底库。

---

## 自动记忆：由运行期决定谁记账

装的时候**不需要知道宿主有没有钩子**。开课跑一条命令，它会告诉你现在走哪条通道、本轮结束要不要手动记账：

```powershell
python core\scripts\mem.py boot
```

| `记忆通道` 那一行 | 含义 | 本轮结束做什么 |
|---|---|---|
| 钩子 工作中 | 宿主钩子在写 L1 | 什么都不用做 |
| 未检测到钩子 / 未工作 | 没有钩子（或钩子没跑） | `mem.py note --text "<一句话总结>"` |
| MCP | 本次调用来自 MCP 服务端 | 调工具 `recalloop_note` |

四条通道，同一套动作：

| 通道 | 需要什么 | 自动化程度 |
|---|---|---|
| 钩子 | 宿主开放钩子 API | 全自动：注入 + 记录 |
| MCP | 宿主支持 MCP | 标准工具；`initialize` 时带服务端说明 |
| 命令行 | 能执行命令 | agent 自己跑 `boot` / `note` |
| 纯文件 | 只能读写文件 | 读 `inject-cache.md`，把摘要写进 `记录/会话日志.md` |

MCP 只配一次，任何支持 MCP 的宿主通用：

```json
{"mcpServers": {"recalloop": {"command": "python",
  "args": ["D:\\插件\\recalloop\\core\\scripts\\mcp_server.py"]}}}
```

无钩子宿主还可以把契约写进宿主的指令文件：

```powershell
python core\scripts\install_adapters.py --rules-file "<宿主的 AGENTS.md / 规则文件>"
```

它只写一段带 `<!-- recalloop:begin/end -->` 标记的块，追加不覆盖，`--remove-rules` 可撤销。

**对账**（否则“自动记忆”只是自说自话）：

```powershell
python core\scripts\mem.py audit --days 7
```

它会指出“有作答但没有对话记录”的日期，并给出补法。

---

## 开始一门课

**插件不建课。** 你自己建一个文件夹，放一个标记文件：

```powershell
mkdir D:\courses\calculus
'{"v":1,"name":"calculus"}' | Out-File -Encoding utf8 D:\courses\calculus\.study-workspace
```

然后把教材放进 `教材\`（或在标记里用 `sources` 指向别处），用 agent 打开这个文件夹即可。

目录怎么组织、产物放哪、怎么覆盖成你已有的结构：见 `core\skills\recalloop\references\layout.md`，或者运行：

```powershell
python core\scripts\artifacts.py layout
```

**已有项目文件夹也能直接用**——不必改名、不必搬文件。只要放一个 `.study-workspace`：

```json
{"v":1,"name":"comfyui",
 "sources":["课程","archive/教程","notes"],
 "layout":{"lesson":"notes/教案","handout":"notes/讲义"},
 "lang":"zh"}
```

- `sources`：检索范围
- `layout`：产物落点覆盖
- `lang`：产物模板语言，`zh`（默认）或 `en`

---

## 素材怎么放

两种方式等价：

1. **手动**——把文件拖进 `教材\`（或 `sources` 里列的目录）
2. **让 agent 放**：

```powershell
python <PACK>\core\scripts\retrieve.py add "<文件或目录>"
```

`add` 会把文件放进课程目录**并增量更新索引**，不需要再单独 `sync`。

### 支持的格式

**插件不要求任何特定引擎。** `probe.py` 打印你这台机器实际有什么，`retrieve.py` 按顺序挑第一个可用的——顺序只是质量偏好，不是硬性要求。什么都不装，纯文本照样能用；装了什么，对应格式就进列表。**永远不会自动安装任何东西。**

| 格式 | 会用到的引擎（有哪个用哪个） |
|---|---|
| md / txt / csv / json / yaml / tex | 内置 |
| html / htm / xhtml | 内置（去标签、去脚本） |
| Jupyter `.ipynb` | 内置 |
| EPUB | 内置（解压 + 去标签），否则 pandoc |
| PDF | pymupdf · pdfplumber · pypdf · PyPDF2 · pdfminer · pdftotext · mutool · LibreOffice |
| 扫描 PDF / 图片 | pytesseract · tesseract 命令行 · easyocr · paddleocr |
| PDF 转图片（供 OCR） | pymupdf · pdftoppm · mutool |
| DOCX | python-docx · docx2txt · pandoc · LibreOffice |
| DOC（旧版） | LibreOffice · pandoc · antiword · catdoc |
| PPTX / PPT | python-pptx · pandoc · LibreOffice |
| XLSX / XLS | openpyxl · pandas · LibreOffice |
| ODT / ODP / ODS / RTF | pandoc · LibreOffice |
| 其它任意格式 | 文本嗅探 → pandoc → LibreOffice |

加一个引擎只要在 `parsers.py` 的登记表里加一条（探测函数 + 读取函数），再挂到对应扩展名的链上，不用改别的文件。

**扫描件自动识别**：PDF 平均每页不足 20 个字符时视为扫描件，转 OCR（最多前 20 页）。

读不了的文件会**列出原因**，不会静默丢掉。

---

## 用法

### 配 agent（OpenCode 等）

用 agent 打开课程文件夹，正常说话。插件会自动：

- 每轮结束时把这一轮写进 `记忆\data\L1`
- 每轮开始时注入学习者画像与进度

技能带**中英双语触发词**，说中文说英文都能触发：

- 英文：*practice, quiz, test me, drill, mastery, next lesson, next topic, what should I learn next, did I learn it, what does the book say, exam paper, exam questions, lesson plan, handout, slides, curriculum, course plan, consolidate*
- 中文：练习、测验、考我、做题、掌握度、下一步学什么、我学会了吗、书上怎么说的、出套卷子、出题、考试题、教案、讲义、课件、课程规划、整合教材

### 不配 agent（纯命令行）

必须在**课程根目录**执行：

```powershell
cd <课程目录>

# 查教材
python <PACK>\core\scripts\retrieve.py search "链式法则" --top 3

# 记一次作答（顺便排下一次复习）
python <PACK>\core\scripts\practice.py record --kp "链式法则" --type procedure --result 1

# 看掌握度
python <PACK>\core\scripts\practice.py list

# 今天要复习什么
python <PACK>\core\scripts\review.py due

# 下一步学什么
python <PACK>\core\scripts\path.py next
```

**不在课程目录里跑会直接报错退出（退出码 2），不会换个地方偷偷写。** 确实要用别处，就显式指定：

```powershell
set MEMORY_ROOT=D:\somewhere\记忆
```

---

## 目录结构

```
recalloop\
├─ README.md              本文件
├─ TECH.md                架构与版本（开发者向）
├─ AGENTS.md              给接手这个包的 agent 的迁移/维护手册
├─ VERSION.json           机器可读清单
├─ THIRD_PARTY_NOTICES.md 算法与第三方声明
├─ LICENSE                MIT
├─ PLAN.md                早期开发记录（历史）
├─ ROADMAP.md             迭代方案与验收记录
├─ install.bat
├─ config.json            可选本机偏好（不含本机路径）
├─ core\
│   ├─ scripts\           14 个 Python 脚本
│   └─ skills\recalloop\ SKILL.md · references\ · templates\（含 en\ 英文模板）
└─ adapters\
    ├─ opencode\memory.ts
    ├─ claude-code\hooks.json
    └─ generic\README.md
```

**程序与数据分离**：包里只有代码，课程与记忆都在课程文件夹。复制一个课程文件夹，它的全部学习记录跟着走。

**语言**：仓库文档以英文为主，本文件双语；给 agent 的提示词（`SKILL.md`）是英文、触发词中英双语；命令行输出是中文；课程目录名（教材/笔记/题库/记忆）属于数据契约，不翻译，可用 `layout` 覆盖。

---

## 命令一览

| 命令 | 用途 |
|---|---|
| `probe.py` | 自检：环境、数据、素材解析能力、建议路线 |
| `artifacts.py new <类型> --topic "…"` | 建产物（exam / lesson / handout / curriculum），`--lang zh\|en` 选模板语言 |
| `artifacts.py layout` | 打印当前工作区生效的目录布局（只报告，不创建） |
| `artifacts.py check <文件>` | 校验结构：缺段、覆盖不足、缺答案、缺评分点、无来源 |
| `artifacts.py bank <试卷>` | 题目抽进 `题库/index.jsonl` |
| `artifacts.py link <文件> --id 01` | 把产物挂到知识点路径 |
| `artifacts.py list` | 列出产物与挂接状态 |
| `brief.py <类型> --topic "…"` | 装配生成输入（素材 + 掌握度 + 错题 + 进度） |
| `retrieve.py sync` | 素材变化后更新索引 |
| `retrieve.py search "…" --top 3` | 检索素材 |
| `retrieve.py add <路径>` | 把素材放进课程并同步 |
| `retrieve.py eval --dataset qa.jsonl` | 评测检索质量（Recall/MRR） |
| `practice.py record …` | 记录作答、判分、排复习 |
| `practice.py list` | 看掌握度 |
| `practice.py qualify --kp …` | 概念/设计类定性合格 |
| `review.py due` | 今天到期 |
| `path.py init / next / done` | 知识点路径 |
| `mem.py boot` | 开课一条命令：画像 + 进度 + 到期复习 + 当前记忆通道 |
| `mem.py note --text "…"` | 无钩子时记账（写 L1，来源标 agent-note，按内容去重） |
| `mem.py audit --days 7` | 对账：有作答但没有对话记录的日期 |
| `mem.py inject` | 只打印注入块（boot 的简化版） |
| `mem.py ingest --file …` | 回填一段对话 |
| `mem.py digest / fact-add / verify` | 固化与断链检查 |
| `mem.py forget --sid …` | 删除某会话记忆（先归档） |
| `mcp_server.py` | MCP 服务端（stdio JSON-RPC），把 boot/note/search/record/due 暴露成工具 |

---

## 常见问题

**黑框一闪一闪？**
插件已经用 `windowsHide` 起进程。还闪就把 `MEMORY_PYTHON` 设成 `python.exe` 的绝对路径，排除 PATH 里的中间层。

**记忆写在哪？**
只写在课程文件夹里（含 `.study-workspace` 的那个）。普通目录一律不写；命令行在非课程目录会直接报错退出。

**掌握度一直是 0？**
还没有作答记录。跑一次 `practice.py record`。

**PDF 内容搜不到？**
先跑 `probe.py` 看「素材解析能力」那一行。如果 PDF 引擎全是（无），装任意一个即可（`pip install pymupdf` / `pip install pypdf`，或装 `pdftotext` 命令）。再确认 `.study-workspace` 里的 `sources` 指对了目录。

**能配别的 agent 吗？**
能。内核是命令行工具，任何能跑命令的 agent 都能用；钩子只是自动化外壳。

**会不会动我别的 agent 的配置？**
不会。安装器里没有任何 agent 名单，它只往你用 `--skills-dir` 指定的目录写；没给目录、也没有唯一候选时只打印说明，一个字节都不写；目标文件不是本插件写的（没有 `@recalloop-managed` 标记）就不覆盖，只报冲突并退出 3。

---

## 许可与第三方

代码由作者编写，**MIT 许可**，见 `LICENSE`。Copyright (c) 2026 Yu Liang。

三个算法都是公开发表的数学模型（BKT、指数遗忘曲线、BM25），按论文独立实现。详见 `THIRD_PARTY_NOTICES.md`。**不含任何第三方源代码**；所有解析引擎都是可选的，只调用、不捆绑。

---

<div id="english"></div>

# English

**Recalloop** = recall + loop. The Chinese name 忆环 is the same two ideas: 忆 (recall) + 环 (loop). The name is the mechanism: search → answer → grade → review → generate, one loop instead of four disconnected tools.

A learning plugin for AI agents. It runs inside the chat: **remember** (memory), **grade** (mastery), **retrieve** before answering and cite the source, and **advance** (review scheduling plus what to learn next). It also generates exams, lesson plans, handouts and curriculum plans from templates.

No UI. No bundled runtime. The only requirement is Python 3.11+.

Version **0.1.0** (first public beta), MIT licence.

---

## What it solves

An ordinary AI conversation forgets everything between turns. Say "that topic from last time" and it has no idea what you mean. Finish a chapter and it cannot tell whether you actually learned it.

This plugin wires four things into the conversation loop:

1. **Memory** — every turn is written to the course folder automatically; the learner profile is injected into the next turn. It survives across sessions.
2. **Mastery** — Bayesian Knowledge Tracing estimates "probability of mastery", with a 0.95 gate. Concept and design knowledge points require a qualitative pass. Answers produced with hints do not count as evidence.
3. **Retrieval** — before answering a question about the materials, the agent searches the source and cites it. If nothing matches, it says so.
4. **Progression** — the knowledge-point path answers "what is next", and a forgetting-curve scheduler decides when to review.

## What it does not do

- No UI, no multi-user, no cloud sync
- No semantic search (keyword BM25 only)
- Does not bundle Python or Node — the user installs the environment
- **Does not write anything outside a course workspace**
- **Does not create courses**: you (or your agent) create the folder and the marker file

---

## Requirements

| Item | Requirement |
|---|---|
| OS | Windows (this version) |
| Python | **3.11 or newer** |
| Third-party packages | **None required** (standard library only) |
| Optional | Whatever parsing / OCR engine you already have — see "Supported formats" |

Bare Python is usable: md / txt / html / ipynb / epub all work. Optional engines only widen the set of readable formats; missing ones change nothing else.

---

## Install

### Option 1: automatic

```powershell
double-click install.bat
```

It checks the Python version, writes optional local preferences, then **probes the skill directories that already exist on the machine**: one candidate is used, several are listed for you to choose, none means it prints manual instructions.

### Option 2: manual (three steps)

```powershell
# 1. write optional local preferences (no machine paths are stored)
python core\scripts\setup_config.py

# 2. install into your host's skill directory (the folder your agent reads skills from)
python core\scripts\install_adapters.py --skills-dir "%USERPROFILE%\.your-agent\skills"

# 3. self-check
python core\scripts\probe.py
```

**There is no agent name anywhere in the installer.** The destination is a directory, so any agent works — including ones the author has never heard of.

If you do not know where that directory is:

```powershell
python core\scripts\install_adapters.py --discover
```

It lists the `<some-dir>/skills` folders that **actually exist** on this machine. When there are several it does not guess; it prints one `--skills-dir` command per candidate.

Options:

| Flag | Purpose |
|---|---|
| `--plugin-dir <dir>` | host loads plugins from a directory: put the hook file there |
| `--hook-json` | host uses a `hooks` block in `settings.json`: print the snippet to merge |
| `--dry-run` | show what would be written, write nothing |
| `--force` | overwrite files that are not ours (backed up first) |

Five hard rules:

| Rule | Behaviour |
|---|---|
| Paths, not names | No agent whitelist in the code; a correct path is all it needs |
| No directory, no writes | No `--skills-dir`, no env var, no single candidate → print only, exit 0 |
| Never creates a directory | Missing target directory → error, exit 2, nothing created |
| Never overwrites a foreign file | Missing `@recalloop-managed` marker → conflict, exit 3, file untouched |
| Forced overwrite backs up | Only with `--force`, after saving `<name>.bak-<timestamp>` |

The environment variable `RECALLOOP_SKILLS_DIR` works too, for scripts and batch installs (the older `STUDYLOOP_SKILLS_DIR` is still accepted).

**Upgrading from an earlier pre-release build:** those files carry no ownership marker, so the first run reports a conflict (exit 3). Once you have confirmed those files really are the ones the plugin installed earlier, run once with `--force`; each old file is backed up as `.bak-<timestamp>` first.

**Restart the agent after installing** so the hook loads (skills are read at the start of the next session).

### About config.json

The pack **runs from any directory**: every script locates the pack root from its own file position, so `config.json` stores no machine path. It holds one optional setting:

```json
{ "v": 1, "default_workspace": "" }
```

`default_workspace` is "which course to use when you are not inside a course folder". It may stay empty. When set, it is an explicit choice, not a silent dumping ground.

---

## Automatic memory: decided at runtime, not at install time

You do **not** need to know whether the host has hooks. One command at the start of a session tells you which channel is active and what to do at the end of the turn:

```powershell
python core\scripts\mem.py boot
```

| The `记忆通道` line says | Meaning | End of turn |
|---|---|---|
| 钩子 工作中 | the host hook is writing L1 | nothing |
| 未检测到钩子 / 未工作 | no hook (or it is not running) | `mem.py note --text "<one line>"` |
| MCP | the call came through the MCP server | call the `recalloop_note` tool |

Four channels, one protocol:

| Channel | Needs | Automation |
|---|---|---|
| Hook | host exposes a hook API | full: inject + record |
| MCP | host supports MCP | standard tools; `initialize` carries server instructions |
| CLI | can run commands | the agent runs `boot` / `note` itself |
| Files only | can read and write files | read `inject-cache.md`, append the summary to `记录/会话日志.md` |

MCP is configured once and works on any host that speaks it:

```json
{"mcpServers": {"recalloop": {"command": "python",
  "args": ["D:\\插件\\recalloop\\core\\scripts\\mcp_server.py"]}}}
```

For a hook-less host you can also write the contract into its instruction file:

```powershell
python core\scripts\install_adapters.py --rules-file "<the host's AGENTS.md / rules file>"
```

It writes one block delimited by `<!-- recalloop:begin/end -->`, appends without touching existing content, and `--remove-rules` takes it out again.

**Reconcile**, otherwise "automatic memory" is self-congratulation:

```powershell
python core\scripts\mem.py audit --days 7
```

It names the days with answers but no dialogue record, and says how to fill the gap.

---

## Start a course

**The plugin does not create courses.** Create a folder yourself and drop in one marker file:

```powershell
mkdir D:\courses\calculus
'{"v":1,"name":"calculus"}' | Out-File -Encoding utf8 D:\courses\calculus\.study-workspace
```

Then put materials into `教材\` (or point `sources` elsewhere in the marker) and open the folder with your agent.

How directories and documents should be organised — and how to override the convention to match an existing project — is documented in `core\skills\recalloop\references\layout.md`, or run:

```powershell
python core\scripts\artifacts.py layout
```

**Existing project folders work as-is** — no renaming, no moving files. Just add a `.study-workspace`:

```json
{"v":1,"name":"comfyui",
 "sources":["课程","archive/教程","notes"],
 "layout":{"lesson":"notes/教案","handout":"notes/讲义"},
 "lang":"zh"}
```

- `sources`: search scope
- `layout`: overrides for artifact destinations
- `lang`: artifact template language, `zh` (default) or `en`

---

## Materials

Two equivalent ways:

1. **Manually** — drop files into `教材\` (or the directories listed in `sources`)
2. **Let the agent do it**:

```powershell
python <PACK>\core\scripts\retrieve.py add "<file-or-directory>"
```

`add` copies the files into the course folder **and updates the index incrementally** — no separate `sync` needed.

### Supported formats

**The plugin does not require any specific engine.** `probe.py` prints what your machine actually has, and `retrieve.py` picks the first available engine per format — the order below is a quality preference, not a requirement. Install nothing and plain text still works; install anything and its format joins the list. **Nothing is ever installed automatically.**

| Format | Engines it will use (whichever is installed) |
|---|---|
| md / txt / csv / json / yaml / tex | built-in |
| html / htm / xhtml | built-in (tags and scripts stripped) |
| Jupyter `.ipynb` | built-in |
| EPUB | built-in (unzip + strip), else pandoc |
| PDF | pymupdf · pdfplumber · pypdf · PyPDF2 · pdfminer · pdftotext · mutool · LibreOffice |
| Scanned PDF / images | pytesseract · tesseract CLI · easyocr · paddleocr |
| PDF page rendering (for OCR) | pymupdf · pdftoppm · mutool |
| DOCX | python-docx · docx2txt · pandoc · LibreOffice |
| DOC (legacy) | LibreOffice · pandoc · antiword · catdoc |
| PPTX / PPT | python-pptx · pandoc · LibreOffice |
| XLSX / XLS | openpyxl · pandas · LibreOffice |
| ODT / ODP / ODS / RTF | pandoc · LibreOffice |
| anything else | text sniffing → pandoc → LibreOffice |

Adding an engine is one registry entry in `parsers.py` (a probe function and a reader function), then attaching it to the extension's chain. No other file changes.

**Scanned documents are detected automatically**: if a PDF yields fewer than 20 characters per page on average, it is treated as scanned and sent to OCR (first 20 pages).

Files that cannot be parsed are **listed with the reason** — nothing is skipped silently.

---

## Usage

### With an agent (OpenCode and similar)

Open the course folder with the agent and talk normally. The plugin automatically:

- writes the turn into `记忆\data\L1` when the turn ends
- injects the learner profile and progress at the start of the turn

The skill ships with **bilingual trigger words**:

- English: *practice, quiz, test me, drill, mastery, next lesson, next topic, what should I learn next, did I learn it, what does the book say, exam paper, exam questions, lesson plan, handout, slides, curriculum, course plan, consolidate*
- Chinese: *练习、测验、考我、做题、掌握度、下一步学什么、我学会了吗、书上怎么说的、出套卷子、出题、考试题、教案、讲义、课件、课程规划、整合教材*

### Without an agent

Run from the **course root**:

```powershell
cd <course-folder>

# search the materials
python <PACK>\core\scripts\retrieve.py search "chain rule" --top 3

# record one answer (also schedules the next review)
python <PACK>\core\scripts\practice.py record --kp "chain rule" --type procedure --result 1

# view mastery
python <PACK>\core\scripts\practice.py list

# what is due today
python <PACK>\core\scripts\review.py due

# what to learn next
python <PACK>\core\scripts\path.py next
```

**Running outside a course folder fails immediately (exit code 2) instead of writing somewhere else.** If you really need another location, say so explicitly:

```powershell
set MEMORY_ROOT=D:\somewhere\记忆
```

---

## Directory structure

```
recalloop\
├─ README.md              this file
├─ TECH.md                architecture and versioning
├─ AGENTS.md              migration / maintenance guide for agents
├─ VERSION.json           machine-readable manifest
├─ THIRD_PARTY_NOTICES.md algorithm and third-party attribution
├─ LICENSE                MIT
├─ PLAN.md                early development record (historical)
├─ ROADMAP.md             iteration plan and acceptance record
├─ install.bat
├─ config.json            optional local preferences (no machine paths)
├─ core\
│   ├─ scripts\           14 Python scripts
│   └─ skills\recalloop\ SKILL.md · references\ · templates\ (with en\)
└─ adapters\
    ├─ opencode\memory.ts
    ├─ claude-code\hooks.json
    └─ generic\README.md
```

**Program and data are separate.** The pack contains code only; courses and memory live in the course folder. Copying a course folder carries all of its learning records.

**Language.** Repository documentation is mainly English; this file is bilingual. The agent-facing prompt (`SKILL.md`) is English with bilingual triggers. Command-line output is Chinese. Course folder names (教材, 笔记, 题库, 记忆, …) are part of the data contract and are not translated — override them with `layout` if you prefer.

---

## Commands

| Command | Purpose |
|---|---|
| `probe.py` | self-check: environment, data, parsing capability, suggested route |
| `artifacts.py new <kind> --topic "…"` | scaffold an artifact (exam/lesson/handout/curriculum), `--lang zh\|en` |
| `artifacts.py layout` | print the effective directory layout (report only) |
| `artifacts.py check <file>` | validate structure: sections, coverage, answers, score points, sources |
| `artifacts.py bank <exam>` | extract questions into `题库/index.jsonl` |
| `artifacts.py link <file> --id 01` | attach an artifact to a knowledge-point path item |
| `artifacts.py list` | list artifacts and their path linkage |
| `brief.py <kind> --topic "…"` | assemble generation input (materials, mastery, errors, progress) |
| `retrieve.py sync` | update the index after material changes |
| `retrieve.py search "…" --top 3` | search materials |
| `retrieve.py add <path>` | copy material into the course and sync |
| `retrieve.py eval --dataset qa.jsonl` | evaluate retrieval quality (Recall/MRR) |
| `practice.py record …` | record an answer, grade it, schedule review |
| `practice.py list` | view mastery |
| `practice.py qualify --kp …` | mark a concept/design knowledge point as qualitatively passed |
| `review.py due` | items due today |
| `path.py init / next / done` | knowledge-point path |
| `mem.py boot` | one command at session start: profile + progress + due + active channel |
| `mem.py note --text "…"` | record without a hook (L1, source agent-note, de-duplicated) |
| `mem.py audit --days 7` | reconcile: days with answers but no dialogue record |
| `mem.py inject` | print the injection block only (boot is the full version) |
| `mem.py ingest --file …` | backfill a conversation |
| `mem.py digest / fact-add / verify` | consolidation and broken-link checks |
| `mem.py forget --sid …` | delete a session's memory (archives first) |
| `mcp_server.py` | MCP server (stdio JSON-RPC) exposing boot/note/search/record/due as tools |

---

## FAQ

**Black console windows flashing?**
The plugin already sets `windowsHide` when spawning Python. If it still flashes, set `MEMORY_PYTHON` to the absolute path of `python.exe` to rule out PATH shims.

**Where is memory written?**
Only inside a course folder (one containing `.study-workspace`). Ordinary directories are never written to; the CLI exits with an error instead.

**Mastery stays at 0?**
There are no recorded answers yet. Run `practice.py record` once.

**PDF content cannot be found?**
Run `probe.py` and look at the "material parsing capability" block. If every PDF engine shows (none), install any one of them (`pip install pymupdf`, `pip install pypdf`, or the `pdftotext` command). Also check that `sources` in `.study-workspace` points at the right directory.

**Can I use it with a different agent?**
Yes. The core is a command-line tool; any agent that can run commands can use it. Hooks are only the automation shell.

**Will installing touch my other agents?**
No. The installer contains no agent list at all; it writes only into the directory you pass with `--skills-dir`. With no directory and no single candidate it prints instructions and writes nothing. A target file that is not ours (no `@recalloop-managed` marker) is never overwritten — it reports a conflict and exits 3.

---

## License and third parties

Written by the author, released under the **MIT licence** — see `LICENSE`. Copyright (c) 2026 Yu Liang.

All algorithms are published mathematical models (BKT, exponential forgetting curve, BM25), implemented independently. See `THIRD_PARTY_NOTICES.md`. **No third-party source code is included**; every parsing engine is optional and merely invoked.
