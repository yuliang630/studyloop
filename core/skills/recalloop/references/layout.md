<!-- @recalloop-managed -->

# Workspace layout convention

This file defines **where things go inside a course working directory**. The plugin does not create the course folder for you, but you must follow this convention when writing, otherwise artifacts scatter.

> Directory names in this document are Chinese literals because they are part of the data contract (the scripts and existing workspaces use them). The names are not translated. If you prefer English directories, override them per workspace — see section 5.

---

## 1. Minimum requirement

The course root must contain one marker file:

```
.study-workspace
```

Example content:

```json
{
  "v": 1,
  "name": "Calculus",
  "sources": ["教材", "资料", "笔记"],
  "lang": "zh"
}
```

- `name`: course name, used in artifact metadata
- `sources`: search scope (relative paths); if omitted, `教材` / `资料` / `笔记` are used
- `lang`: artifact template language, `zh` (default) or `en`
- No marker file → the plugin treats the directory as "not a course workspace": no memory is written, no artifacts are managed

---

## 2. Default layout

```
<course>\
├─ .study-workspace          marker (required; you or the agent write it)
├─ 教材\                     original materials, read-only
├─ 资料\                     other people's slides, handouts, saved web pages
├─ 笔记\                     your own notes
│   ├─ 讲义\                 plugin artifact: handouts
│   └─ 教案\                 plugin artifact: lesson plans
├─ 题库\
│   ├─ 参考题\               practice questions
│   ├─ 考试卷\               full exam papers
│   └─ index.jsonl           question index (written by `bank`)
├─ 实验\                     one subdirectory per experiment
├─ 记录\
│   ├─ 复习计划.md           human-readable review schedule
│   └─ brief-*.md            generation briefs (written by `brief.py`)
├─ 产出\                     exports: docx / Anki / images
└─ 记忆\data\                written by the plugin automatically; never edit by hand
```

**When a directory does not exist, the artifact commands create the ones they need.** All other directories are your decision.

---

## 3. What goes where

| Content | Location | Who writes it |
|---|---|---|
| Original materials | `教材\` | you |
| Other people's handouts, slides | `资料\` | you |
| Your own notes | `笔记\` | you or the agent |
| Handouts (artifact) | `笔记\讲义\` | agent, via `artifacts.py new handout` |
| Lesson plans (artifact) | `笔记\教案\` | agent, via `artifacts.py new lesson` |
| Exam papers (artifact) | `题库\考试卷\` | agent, via `artifacts.py new exam` |
| Loose practice questions | `题库\参考题\` | you or the agent |
| Question index | `题库\index.jsonl` | `artifacts.py bank` |
| Experiment records | `实验\<date>-<topic>\` | you |
| Review schedule | `记录\复习计划.md` | you or a script |
| Generation brief | `记录\brief-*.md` | `brief.py` |
| Exports | `产出\` | you |
| Memory | `记忆\data\` | the plugin, **never by hand** |

---

## 4. Naming

| Kind | Pattern | Example |
|---|---|---|
| Exam | `<date>-<topic>.md` | `2026-11-27-ControlNet.md` |
| Lesson plan | `<date>-<topic>.md` | `2026-11-27-KSampler.md` |
| Handout | `<topic>.md` | `ComfyUI-basics.md` |
| Curriculum | `课程规划.md` (single file, overwritten in place) | — |
| Experiment | `<date>-<topic>/` | `2026-11-03-prompt-experiment/` |

Dates are always `YYYY-MM-DD`.

---

## 5. Adapting an existing directory structure

If you already have your own layout (for example `courses\`, `notes\`, `experiments\`), **do not rename anything**. Override the destinations in `.study-workspace`:

```json
{
  "v": 1,
  "name": "comfyui",
  "sources": ["课程", "archive/tutorials", "notes"],
  "layout": {
    "exam": "题库/考试卷",
    "lesson": "notes/lesson-plans",
    "handout": "notes/handouts",
    "curriculum": "记录",
    "bank": "题库/index.jsonl"
  }
}
```

Anything not overridden keeps its default.

---

## 6. How the agent uses this convention

1. When unsure about the layout, run:

   ```bash
   python <PACK>\core\scripts\artifacts.py layout
   ```

   It prints the **layout actually in effect** for this workspace and marks which directories are missing.

2. Before writing an artifact, read the `layout` output and write to those destinations. **Do not invent directory names.**

3. If an artifact directory does not exist, `artifacts.py new` creates it. **Do not create the other directories on the user's behalf.**

4. If the user's structure conflicts with this convention, **ask the user first**, then override via `layout`. Never move existing files without permission.
