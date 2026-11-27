# StudyPack · Technical Reference

> Version 2.0.1 · 2026-11-27
> Audience: developers and agents who will maintain or iterate on this pack. Read this to understand **what it is, how it is organized, how it runs, and where to change things**.

---

## 1. Architecture in one sentence

**Host agent (chat) + thin adapters (hooks / command bridges) + standard-library-only scripts (capabilities) + plain files in the course folder (data).**

No long-running service, no database, no required third-party dependency.

---

## 2. Layers

```
L1 Host        AI agent (OpenCode / Claude Code / …): chat, model, tool execution
L2 Adapters    adapters/opencode/memory.ts (hooks)
               adapters/claude-code/hooks.json (command bridge)
               Responsibility: fetch session messages, forward to scripts, read cache and inject.
               Contains no business logic.
L3 Capability  core/scripts/*.py (standard library only)
               Responsibility: memory, grading, review, retrieval, path, scaffolding.
L4 Data        <course>/记忆/data/{L1,L2,L3,state}
               Responsibility: persistence; all plain text.
```

**Key constraint**: swapping agents replaces only L2 (about 250 lines); L3 stays untouched.

---

## 3. Modules

| File | Responsibility | Entry points |
|---|---|---|
| `paths.py` | single source of truth for the memory root | `resolve_root()`: `MEMORY_ROOT` > workspace marker > `default_workspace`; `require_root()` exits 2 when none applies (no fallback) |
| `mem.py` | memory read/write | `ingest`, `inject`, `digest`, `fact-add`, `verify`, `forget` |
| `mastery.py` | mastery grading (pure) | `bkt_state()`, `compute_mastery()`, `gate_threshold()`, `is_mastered()`, `next_action()` |
| `practice.py` | answer records and status | `record` / `status` / `list` / `qualify` |
| `srs.py` | forgetting-curve scheduling (pure) | `rating_for()`, `next_interval_days()`, `next_state()`, `update_for()` |
| `review.py` | due list | `due` / `stats` / `reset` |
| `path.py` | knowledge-point path | `init` / `next` / `done` |
| `retrieve.py` | retrieval | `index`/`sync`/`search`/`eval`/`stats`/`add`; BM25, CJK bigrams |
| `parsers.py` | material parsing layer | engine registry (probe + reader per engine) + per-extension chains + generic fallback; skips unreadable files with reasons |
| `artifacts.py` | artifact scaffolding | `new` / `list` / `layout` / `check` / `bank` / `link` |
| `brief.py` | generation-input assembly | materials + mastery + errors + progress → `记录/brief-*.md` |
| `probe.py` | self-check | environment, data volume, suggested route |
| `setup_config.py` | write machine config | `config.json` |
| `install_adapters.py` | deploy adapters and skill | copies plugin, replaces `__PACK_ROOT__` and `<PACK>` |

---

## 4. Data contracts

Change a field name only after changing this section.

### L1 · raw trace (append-only, never modified)
```json
{"v":1,"turn_id":"trn_...","scope":"default","sid":"ses_...","surface":"chat",
 "started_at":"local ISO","ended_at":"local ISO","msg_ids":["msg_a"],
 "msg_count":2,"excerpt":"[user] … [assistant] …"}
```
- `excerpt` is capped at 800 characters — it is an **excerpt, not a summary**
- only `type ∈ {user, assistant}` are kept; reasoning and tool fragments are dropped
- timestamps originate from message `time.created` as **millisecond integers** and must be scaled before use

### L2 · facts (each carries evidence)
```
- 2026-11-27 · fact text <!-- ev: trn_aaa,trn_bbb -->
```
`mem.py verify` checks that every `ev` exists in L1.

### L3 · profile
`profile.md` (≤1000 characters, injected every turn), `recent.md` (last week).

### state · runtime state
| File | Content |
|---|---|
| `cursors.json` | per-session cursor plus a seen-set (idempotency) |
| `attempts.jsonl` | one record per answer: kp/type/correct/hints/ts |
| `reviews.json` | per knowledge point: half-life, interval, due_at, reps, lapses |
| `path.json` | knowledge-point path (id/title/done/artifact) |
| `index.json` | retrieval index (chunks + df + file fingerprints) |
| `inject-cache.md` | cached injection block |

### Artifacts
| Kind | Default location |
|---|---|
| exam | `题库/考试卷/<date>-<slug>.md` |
| lesson | `笔记/教案/<date>-<slug>.md` |
| handout | `笔记/讲义/<slug>.md` |
| curriculum | `记录/课程规划.md` |
| question bank | `题库/index.jsonl` |

All five can be overridden per workspace through the `layout` field in `.study-workspace` (see `core/skills/study-loop/references/layout.md`).

**Templates are bilingual.** `templates/` holds the Chinese skeletons, `templates/en/` the English ones. `artifacts.py new` picks the language from `--lang`, then the workspace marker's `lang` field, then Chinese by default. The validator and the question-bank extractor accept **either** language: section names are matched against a canonical Chinese name plus an alias table (`ALIASES` in `artifacts.py`), and the answer labels accept `答案：` / `Answer:` and `评分点：` / `Scoring:`. A document may even mix them.

---

## 5. Runtime flow

### One chat turn

```
user message
  → [context hook] if the cache is stale (L3 / path / reviews changed) → mem.py inject --out
                   read cache → splice into system
  → [agent] retrieve → answer with citations → ask a question → grade (practice record)
  → [idle hook] session.context → mem.py ingest --refresh-out
                write L1 and rebuild the injection cache (one Python process per turn)
```

### Workspace resolution

```
sessionID → session.get().location.directory
          → contains .study-workspace ? <dir>/记忆 : write nothing
```

Command line, in priority order, all of them explicit:

```
MEMORY_ROOT (environment)  >  <cwd>/记忆 when .study-workspace exists  >  config default_workspace
none of the above → exit code 2 with the reason; nothing is written anywhere
```

Ordinary directories are never written to. There is **no fallback root** — the earlier `%LOCALAPPDATA%\StudyPack\记忆` fallback was removed in 2.0.1, because a learning plugin that quietly collects data in an arbitrary directory is a liability. `probe.py` is the one exception: it can run anywhere and simply reports "not located".

---

## 6. Key decisions

| # | Decision | Reason | Cost |
|---|---|---|---|
| 1 | standard library only | the user installs Python and nothing else | routing, tokenizing and BM25 are handwritten |
| 2 | files as the database | readable, editable, copyable, diffable | no concurrency control |
| 3 | write only inside course folders | a learning plugin should not collect general chat | ordinary conversations have no memory |
| 4 | keyword retrieval | no GPU; embeddings are impractical here | semantic queries miss |
| 5 | thin adapters, logic in scripts | swapping agents touches only the shell | one extra process per turn |
| 6 | hints invalidate evidence | prevents "mastery by hint" | may feel strict |
| 7 | BKT instead of weighted accuracy | uncertainty is expressed probabilistically instead of by ad-hoc caps | four parameters to tune |
| 8 | forgetting curve instead of SM-2 tables | one interpretable quantity (half-life) | no per-user fitting yet |
| 9 | plugin never creates courses | it is a plugin, not a course generator | the user (or the agent) must create the folder and marker |
| 10 | layout is a convention that can be overridden | existing projects must not be restructured | one more field to understand |

---

## 7. Known limitations

1. Windows only (path separators, `windowsHide`, `.bat`).
2. No UI, no multi-user.
3. Long turns keep only an 800-character excerpt; full products should be written to files.
4. Keyword retrieval only; CJK is tokenized as bigrams; no synonyms.
5. `path.json` completion requires an explicit `path.py done`; it is not inferred.
6. Uninstalling never deletes data (`记忆/` stays).
7. Artifact bodies are produced by the agent; the pack only provides structure, inputs and validation.

---

## 8. How to change things

### Add a command
1. Implement `cmd_xxx(args)` in the relevant script
2. Register it in `build_parser()`
3. Add an acceptance test
4. Update section 3 here and the command table in `README.md`

### Add an agent adapter
1. Create `adapters/<agent>/`
2. Do exactly two things: call `mem.py inject` at session start (stdout becomes context), call `mem.py ingest` at turn end
3. Do not put business logic in it and do not assemble the memory block yourself
4. Register it in `README.md` and `install_adapters.py`

### Change grading rules
- Only change `mastery.py`
- Run `test_mastery.py` afterwards (BKT formula self-check plus gate behaviour)
- Never scatter grading rules into `practice.py`

### Change retrieval
- Only change `retrieve.py`
- Run `retrieve.py eval`; recall must not regress

### Add a parsing engine
- One entry in `ENGINES` (`parsers.py`): a `probe` callable and a `read` callable returning `(text, engine_label)`
- Attach it to the extension's chain in `CHAINS`, in preference order
- Run `test_parsers_registry.py`; it checks registry integrity (every chained name is registered, every entry has both callables)
- Never make an engine required: `probe` returning false must leave the rest of the pipeline working

### Change directory conventions
- Edit `references/layout.md` and `DEFAULT_LAYOUT` in `artifacts.py`
- Keep both in sync, otherwise the documentation lies

---

## 9. Tests

| Test | Coverage |
|---|---|
| `test_mastery.py` | BKT formula and gates (19) |
| `test_practice.py` | practice loop (16) |
| `test_mem_ingest.py` | ingest / inject (11) |
| `test_p7_srs_path.py` | review and path (12) |
| `test_p2_retrieve.py` | retrieval (8) |
| `test_parsers.py` | md / docx / pdf / OCR through retrieve (9) |
| `test_parsers_registry.py` | engine registry integrity, html / ipynb / epub / sniffing (18) |
| `test_e2e_formats.py` | html / ipynb / epub indexed and retrieved end to end (4) |
| `test_m1_artifacts.py` | scaffold new/list (17) |
| `test_m2_brief.py` | input assembly (13) |
| `test_m3_check.py` | validator, positive and seven negatives (8) |
| `test_m4_writeback.py` | bank / link (11) |
| `test_bilingual_artifacts.py` | zh/en templates, validation and bank extraction in both languages (13) |
| `test_path_guard.py` | no writes outside a course; explicit MEMORY_ROOT; probe anywhere (8) |
| `test_workspace.mjs` | course binding (5) |
| `test_no_workspace.mjs` | no writes outside a course (3) |

**195 assertions. Run the full suite before releasing.**

---

## 10. Version history

| Version | Date | Content |
|---|---|---|
| **2.0.1** | 2026-11-27 | Bilingual README and bilingual artifact templates plus validator (zh/en section names and answer labels); English documentation and bilingual skill triggers; parsing layer rebuilt as an engine registry (about 20 optional engines, built-in html/ipynb/epub, text sniffing and generic converters); **no fallback memory root** — the CLI exits 2 outside a course; `config.json` no longer records machine paths; references installed together with the skill; MIT `LICENSE` |
| 2.0.0 | 2026-11-27 | Artifact scaffolding: four templates (exam / lesson / handout / curriculum), `artifacts.py` (new/list/layout/check/bank/link), `brief.py` input assembly; the validator rejects missing sections, insufficient coverage, missing answers, missing score points and missing citations; no new required dependency |
| 1.2.0 | 2026-11-27 | Material parsing layer: multi-engine priority chains (PDF / DOCX / PPTX / XLSX / images), automatic OCR for scanned pages, `retrieve.py add`, explicit skip reporting |
| 1.1.0 | 2026-11-27 | Algorithm replacement: mastery moved to Bayesian Knowledge Tracing, review moved to an exponential forgetting curve; all dependence on previous rule parameters removed |
| 1.0.0 | 2026-11-27 | First complete version: three-layer memory, mastery grading, practice loop, review scheduling, knowledge-point path, retrieval and evaluation, multi-agent adapters, course workspace, migration documentation |

### Fixes during development
Millisecond timestamp crash · reasoning leakage into excerpts · backfill storm on plugin load · duplicate writes on hot reload · string-based sorting · mixed time zones · entire long turn lost when the window contained no user message · plugin resolved its root per process instead of per session · hardcoded retrieval directories · `path.py` wrote to the wrong file handle · `inject` returned early and swallowed progress · `<PACK>` placeholder left unreplaced in the installed skill · two Python spawns per turn merged into one · console window flashes (`windowsHide`)
