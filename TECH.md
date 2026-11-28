# Recalloop · Technical Reference

> Version 0.2.0 (beta) · 2026-11-28
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
| `mcp_server.py` | MCP transport shell | stdio JSON-RPC 2.0; tools `boot`/`note`/`search`/`record`/`due`, resources `recalloop://profile`, `recalloop://due`; **no business logic, forwards to the scripts** |
| `brief.py` | generation-input assembly | materials + mastery + errors + progress → `记录/brief-*.md` |
| `probe.py` | self-check | environment, data volume, suggested route |
| `setup_config.py` | write machine config | `config.json` |
| `install_adapters.py` | deploy into a directory you name | `--skills-dir` / `RECALLOOP_SKILLS_DIR` / single discovered candidate; `--plugin-dir` and `--hook-json` are optional; **no agent names in the code**; never creates the target directory, never overwrites a file without the `@recalloop-managed` marker (exit 3), `--force` backs up first |

---

## 4. Data contracts

Change a field name only after changing this section.

### L1 · raw trace (append-only, never modified)
Two sources share the file: hook/CLI ingest (`source` absent, full `msg_ids`) and agent summaries (`source: "agent-note"`, `msg_count: 0`, `turn_key` for de-duplication). Never present a note as a verbatim transcript.
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
`mem.py verify` checks that every `ev` exists in L1. **L2 facts are not injected** into the turn; query them on demand with `mem.py fact-list` or by retrieval.

### L3 · profile
`profile.md` (≤1000 characters) and `recent.md` (≤215 characters, last 7 days). Both are rebuilt by `mem.py profile --build` — after `digest` or on demand — and injected every turn. The whole block has a 1500-character budget: 1000 (profile) + 215 (recent) + 200 (progress) + 85 (template overhead).

### state · runtime state
| File | Content |
|---|---|
| `cursors.json` | per-session cursor plus a seen-set (idempotency) |
| `attempts.jsonl` | one record per answer: kp/type/correct/hints/ts |
| `reviews.json` | per knowledge point: half-life, interval, due_at, reps, lapses |
| `path.json` | knowledge-point path (id/title/done/artifact) |
| `index.json` | retrieval index (chunks + df + file fingerprints) |
| `inject-cache.md` | cached injection block (written by `mem.py boot --out` or the hook) |
| `hook.json` | hook heartbeat: `last_ingest_at`, `turns`; `boot` reads it to decide whether the agent must record manually |

### Artifacts
| Kind | Default location |
|---|---|
| exam | `题库/考试卷/<date>-<slug>.md` |
| lesson | `笔记/教案/<date>-<slug>.md` |
| handout | `笔记/讲义/<slug>.md` |
| curriculum | `记录/课程规划.md` |
| question bank | `题库/index.jsonl` |

All five can be overridden per workspace through the `layout` field in `.study-workspace` (see `core/skills/recalloop/references/layout.md`).

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

Ordinary directories are never written to. There is **no fallback root** — the earlier `%LOCALAPPDATA%` fallback root was removed before the first public release, because a learning plugin that quietly collects data in an arbitrary directory is a liability. `probe.py` is the one exception: it can run anywhere and simply reports "not located".

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
- Run the suite afterwards: `python -m unittest discover -s tests -p "test_*.py"` (BKT formula self-check plus gate behaviour)
- Never scatter grading rules into `practice.py`

### Change retrieval
- Only change `retrieve.py`
- Run `retrieve.py eval`; recall must not regress

### Add a parsing engine
- One entry in `ENGINES` (`parsers.py`): a `probe` callable and a `read` callable returning `(text, engine_label)`
- Attach it to the extension's chain in `CHAINS`, in preference order
- Run the suite: `python -m unittest discover -s tests -p "test_*.py"`; add a registry case when you register a new engine
- Never make an engine required: `probe` returning false must leave the rest of the pipeline working

### Change directory conventions
- Edit `references/layout.md` and `DEFAULT_LAYOUT` in `artifacts.py`
- Keep both in sync, otherwise the documentation lies

---

## 9. Tests

`python -m unittest discover -s tests -p "test_*.py"` — **41 cases across 10 files**, all green.

| Test file | Coverage |
|---|---|
| `tests/test_baseline.py` | CP1 baseline: the D-1 assertions (now green), sample structure, `init` tree |
| `tests/profile/spec/test_schema_pin.py` | A18: schema sha256 and budget constants pinned to literals |
| `tests/profile/spec/test_template.py` | A19: template constants vs the frozen spec, render wiring |
| `tests/profile/spec/test_trim.py` | A4 / A4b / A5 / A5b / A6: paragraph-level trimming and block truncation |
| `tests/profile/spec/test_roundtrip.py` | build → check in three data states; template/regex drift guard |
| `tests/profile/check/test_probe.py` | A20: probe isolation (no `import mem`, AST-checked), init skeleton, scope |
| `tests/profile/check/test_samples.py` | A10–A13: four sample verdicts |
| `tests/profile/mcp/test_mcp.py` | A7 / A8 / A9: MCP profile resource and scope resolution |
| `tests/adapter/test_adapter.py` | A23: adapter cache paths follow `RECALLOOP_SCOPE` (static check) |
| `tests/profile/l2/test_docs.py` | A24: L2 facts are not injected; docs match code |

Fixtures live in `tests/fixtures/`, samples in `tests/samples/`, baseline hashes in `tests/HASHES.txt`.

**Run the full suite before releasing.**

---

## 10. Version history

**First public release: 0.1.0 (beta).** The code was written and revised within a single day, 2026-11-27. Earlier internal numbers were never published and are not kept as versions: a version number is a promise to users, not a diary entry.

| Version | Date | Content |
|---|---|---|
| **0.1.0** (beta) | 2026-11-27 | First public release: three-layer memory, BKT mastery, BM25 retrieval, forgetting-curve review, knowledge-point path, artifact scaffolding (bilingual templates + validator), path-based host-neutral installer, four memory channels (hook / MCP / CLI / files only), bilingual README, MIT licence |
| **0.2.0** (beta) | 2026-11-28 | L3 profile layer completed: `mem.py profile --build` generates a four-section profile and a recent-activity digest from L1 / L2 / state; `profile --check` validates structure and returns four verdicts; scope resolution unified in `paths.resolve_scope` (`config.json`'s `scope` field retired); a 41-case suite added under `tests/`; profile claims and test inventory aligned across README / TECH / ROADMAP |

### What was built that day (internal notes, no version numbers)

- base: three-layer memory, mastery grading, practice loop, review scheduling, knowledge-point path, retrieval and evaluation, agent adapters, course workspace, migration docs
- algorithms: mastery moved to Bayesian Knowledge Tracing; review moved to an exponential forgetting curve
- parsing: engine registry (about 20 optional engines) with built-in html / ipynb / epub, text sniffing and generic converters
- artifacts: four templates, `new/list/layout/check/bank/link`, `brief.py`, validation in Chinese and English, question bank, path linkage
- installer: from "install into whatever directory happens to exist" to a three-name whitelist, then to paths only
- memory: runtime channel detection (`boot`), `note` for hook-less hosts, `audit` reconciliation, `mcp_server.py`, hook heartbeat
- documentation: English rewrite, then a bilingual README; macOS/Linux still unsupported

### Fixes during development
Millisecond timestamp crash · reasoning leakage into excerpts · backfill storm on plugin load · duplicate writes on hot reload · string-based sorting · mixed time zones · entire long turn lost when the window contained no user message · plugin resolved its root per process instead of per session · hardcoded retrieval directories · `path.py` wrote to the wrong file handle · `inject` returned early and swallowed progress · `<PACK>` placeholder left unreplaced in the installed skill · two Python spawns per turn merged into one · console window flashes (`windowsHide`)
