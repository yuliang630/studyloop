---
name: study-loop
description: Study loop — search the course materials, answer with citations, quiz, grade mastery, then advance or review; also generates exams, lesson plans, handouts and curriculum plans from templates. Use when the user asks for practice, a quiz, to be tested on a topic, asks "what should I learn next" or "how well do I know this", asks a question about the course materials, or asks for an exam paper, lesson plan, handout, slides or curriculum plan, or asks to consolidate the materials into a course. Trigger words (English): practice, quiz, test me, drill, mastery, next lesson, next topic, what should I learn next, did I learn it, what does the book say, exam paper, exam questions, lesson plan, handout, slides, curriculum, course plan, consolidate. Trigger words (Chinese): 练习、测验、考我、做题、掌握度、下一步学什么、我学会了吗、书上怎么说的、出套卷子、出题、考试题、教案、讲义、课件、课程规划、整合教材。
---

<!-- @studyloop-managed -->

# Study loop (study-loop)

This directory is a **course workspace**. This skill defines how to search the materials, how to cite, how to grade, and when to advance.

`<PACK>` in the commands below is the root of the plugin pack (written into `config.json` at install time).

---

## 1. Answering questions about the materials: search first

**Any question about course content must be searched before it is answered.**

```bash
python <PACK>\core\scripts\retrieve.py search "<keywords>" --top 3 --json
```

Rules:

1. **Search before answering.** Never explain the materials from memory.
2. **Every factual claim carries a source**: `(source: 教材/chapter-02.md)`.
3. **If nothing matches, say so**: "the materials do not cover this directly", then you may add general knowledge, clearly labelled "the following is not from this course's materials".
4. **Never fake a citation.** A passage you did not retrieve cannot appear as a quotation.
5. Search results are fragments; **the original may carry context.** If unsure, search again with different keywords.

### How to read each file format (do not guess)

When you are unsure how a file should be read, check what this machine can do:

```bash
python <PACK>\core\scripts\probe.py
```

The "material parsing capability" block lists, format by format, exactly which engines this machine has (PDF, scanned pages, DOCX, PPTX, XLSX, legacy Office, e-books) and which are missing. The list is not a requirement — it is what was found.

**Indexing picks the engine by priority automatically**, and any file it cannot read is listed in the skip report together with the reason — nothing is dropped silently.

What you must do: **do not guess which tool to use, and do not hand-write a parser.** Call `retrieve.py` and let it use what the machine has.

When materials are added or changed, sync incrementally first:

```bash
python <PACK>\core\scripts\retrieve.py sync --root .
```

---

## 2. Quizzing and grading

### The knowledge-point type decides how it is graded

| Type | Grading | Gate |
|---|---|---|
| `memory` | Quantitative: BKT posterior probability of mastery | 0.95 |
| `procedure` | Quantitative: same as above | 0.95 |
| `concept` | **Qualitative**: can the learner explain it themselves | probability not used |
| `design` | **Qualitative**: same as above | probability not used |

### One answer, step by step

1. Ask **one** question (never a batch)
2. Wait for the answer
3. Record it:

```bash
python <PACK>\core\scripts\practice.py record --kp "<knowledge point>" --type <type> --result <1|0|0.5> [--hints N]
```

4. Act on the returned `action`:

| Returned | What to do |
|---|---|
| `advance` | Move to the next knowledge point; **do not re-explain what already passed** |
| `practice` | Change the wording or lower the step; **do not repeat the same question** |

### Five hard rules

1. **Never answer for the learner**, and never show the answer before asking.
2. **Never substitute "I think you understand" for grading.** Only the value returned by `practice.py` counts.
3. **If a hint was used, record `--hints N` honestly.** It is stored, but it does not count as evidence.
4. **Concept and design knowledge points must not be multiple choice.** Ask "explain X in your own words"; when it passes, run:

```bash
python <PACK>\core\scripts\practice.py qualify --kp "<knowledge point>" --note "<evidence>"
```

5. **One or two correct answers do not mean mastery** (capped at 0.5 / 0.8). Either collect more evidence or say plainly "not yet".

---

## 3. Checking status

```bash
python <PACK>\core\scripts\practice.py list
python <PACK>\core\scripts\practice.py status --kp "<knowledge point>"
```

When the learner asks "how well do I know this", run `list` and report what it says. Do not answer from impression.

## 3b. Review and path

Every `practice.py record` schedules the next review automatically (forgetting curve, half-life). Due list:

```bash
python <PACK>\core\scripts\review.py due        # due today
python <PACK>\core\scripts\review.py stats      # all scheduled items
```

**At the start of every session, check what is due.** Review first, then teach something new.

The knowledge-point path is parsed from a course file and answers "what next":

```bash
python <PACK>\core\scripts\path.py init         # first run: parse 课程\00-学习路线.md
python <PACK>\core\scripts\path.py next         # next lesson
python <PACK>\core\scripts\path.py done --id 01 # mark a lesson as passed
```

**After a lesson passes its five-question check you must run `path.py done --id <lesson>`**, otherwise the path never advances.

---

## 4. Memory

### Start of session: one command

```bash
python <PACK>\core\scripts\mem.py boot
```

It returns the learner profile, progress, due reviews — **and tells you whether a hook is doing the recording for you**. Follow that line:

| The `记忆通道` line says | What you do at the end of the turn |
|---|---|
| 钩子 工作中 | nothing; the hook already wrote L1 |
| 未检测到钩子 / 未工作 | run `mem.py note --text "<one-line summary>"` |
| MCP | call `studyloop_note` (the tool, not the CLI) |

### Recording when there is no hook

```bash
python <PACK>\core\scripts\mem.py note --text "what was asked, what was done, what the result was"
```

- `note` writes an L1 record with `source: agent-note` — it is **your summary, not the raw transcript**; never present it as a verbatim record.
- Repeating the same `sid` + text is de-duplicated by `turn_key`; `--force` overrides that.
- If the host gives you a transcript file, prefer the real thing:

```bash
python <PACK>\core\scripts\mem.py ingest --file <transcript> --sid <session>
```

### Checking what actually got recorded

```bash
python <PACK>\core\scripts\mem.py audit --days 7
```

It compares answers (`attempts.jsonl`) against L1 and names the days with no record. **When audit reports a gap, say so** — do not let the learner believe memory was kept when it was not.

### L2 facts

- Only conclusions worth keeping long term (not process) go into L2, and each must carry evidence:

```bash
python <PACK>\core\scripts\mem.py digest --hours 24
python <PACK>\core\scripts\mem.py fact-add --text "<conclusion>" --evidence trn_xxx
python <PACK>\core\scripts\mem.py verify
```

Consolidation criteria: **long-lived + backed by L1 evidence + not private + not procedural**. If any one is missing, do not write it.

---

## 5. Generating artifacts (exam / lesson plan / handout / curriculum)

All four kinds follow the same five steps: **assemble input → create file → fill the middleware → validate → write back**.

> **When the destination is unclear, run `python <PACK>\core\scripts\artifacts.py layout` first** and write to the directories it prints.
> How directories are organised, and how to override the convention to match an existing project, is in `references/layout.md` next to this file.
> **Do not invent directory names.** If the user's layout conflicts with the convention, ask the user first.

### 1. Assemble the input (mandatory)

```bash
python <PACK>\core\scripts\brief.py <exam|lesson|handout|curriculum> --topic "<topic>"
```

It writes `记录/brief-*.md` containing: material excerpts with sources, learner mastery, recent mistakes, progress and due reviews.
**Write from that brief. Do not invent content.**

### 2. Create the file

```bash
python <PACK>\core\scripts\artifacts.py new <kind> --topic "<topic>" [--lang zh|en]
```

The template language follows, in order: `--lang`, the workspace marker's `lang` field, then Chinese. Use the learner's language — do not produce a Chinese skeleton for an English learner.

### 3. Fill the middleware before the body

| Artifact | Middleware (fill first) |
|---|---|
| Exam | Exam blueprint / 命题蓝图 (knowledge point × question type × difficulty × count) |
| Handout | Glossary / 术语表 + Outline / 大纲 |
| Lesson plan | Objectives / 目标 · Difficult points / 难点 · Prerequisites / 前置 |
| Curriculum | Knowledge-point table / 知识点表 (with prerequisite relations) |

### 4. Validate

```bash
python <PACK>\core\scripts\artifacts.py check <file>
```

Fix until it exits 0. It catches: missing section, insufficient coverage, missing answer, missing score point, missing source.

### 5. Write back

```bash
python <PACK>\core\scripts\artifacts.py bank <exam>          # questions into the bank
python <PACK>\core\scripts\artifacts.py link <file> --id 01  # attach to a path item
```

### Hard rules

1. **Never skip `brief.py`.** Writing without assembled input is fabrication.
2. **Never skip `check`.** A failing validation is not a delivery.
3. **An exam must cover every knowledge point in its blueprint** — 100% coverage.
4. **Every handout chapter must carry `**来源**：`** (or `**Source**:`) and a real source; if there is none, write "to be verified" and explain why.
5. **Write artifacts only inside the course directory**, nowhere else.
6. **Either language is valid.** Section names are accepted in Chinese or English (`## 命题蓝图` or `## Exam blueprint`), answer labels as `- 答案：` or `- Answer:`. Write in the learner's language and keep one document consistent.

## 6. Which directory to run in

Run in the **course workspace root** (the folder containing `.study-workspace`).
The scripts write into `<course>\记忆\` automatically; no environment variable is needed.

Running elsewhere **fails with exit code 2** and writes nothing — there is no fallback root. If you must point somewhere else, do it explicitly with `MEMORY_ROOT`. **`cd` into the course directory before doing anything.**
