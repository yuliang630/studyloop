# StudyPack v2.0 · Iteration Plan and Roadmap

> Started: 2026-11-27 · Owner: the main agent · Status: **complete (M0–M5), 151 regression assertions green**
> This file is the single source of truth for this iteration. To change it, follow the change process in section 8.

---

## 1. Goal

**Add software support for "artifact generation": the agent should be able to produce exams, lesson plans, handouts and curriculum plans in a fixed structure, while the plugin handles input assembly, structural constraints, validation and write-back.**

### This iteration delivers software, not teaching content

| It is | It is not |
|---|---|
| A command-line tool (create, validate, list artifacts) | The author writing a real exam |
| Template files (structural skeletons) | The author writing handout prose |
| An input assembler (materials + mastery + errors → brief) | The author teaching a lesson |
| Automated validation (missing sections, incomplete coverage, missing citations) | The author judging quality by hand |

**Acceptance is proven by tests, not by producing a finished artifact.**

---

## 2. Scope

### In scope

| # | Deliverable | Form | Notes |
|---|---|---|---|
| D1 | `core/scripts/artifacts.py` | CLI | `new` / `check` / `list` for four artifact kinds |
| D2 | `core/scripts/brief.py` | CLI | Assembles the generation brief: material excerpts + mastery + errors + path position |
| D3 | `core/skills/study-loop/templates/` | 4 Markdown skeletons | exam / lesson / handout / curriculum |
| D4 | Write-back | Data contract | Exam questions → question-bank index; lesson/curriculum → linked to `path.json` |
| D5 | Tests | Scripts | Template rendering, validator positives and negatives, brief assembly |
| D6 | Documentation | Edits | README command table, TECH module table, VERSION 2.0.0 |

### Out of scope

- No generation engine (the body text is written by the agent and the model)
- No methodology documents (the existing skill rules are enough; this iteration only adds templates and validation)
- No sample exams or sample handouts as acceptance evidence
- No changes to the internals of `mem.py` / `mastery.py` / `srs.py` / `retrieve.py`
- No UI, no question-bank database

---

## 3. Roadmap

```
M1 artifacts skeleton ──► M2 input assembly ──► M3 validation ──► M4 write-back ──► M5 close-out
```

| Milestone | Content | Effort | Acceptance |
|---|---|---|---|
| M1 | `artifacts.py`: four templates + `new` / `list` | 1 day | ✅ 17/17: all four kinds generate, placeholders replaced, duplicates refused, `--force`, `list`, non-course directory refused |
| M2 | `brief.py`: assemble the input brief | 1 day | ✅ 13/13: template requirements, material excerpts, learner state, errors, progress, due reviews; runs for all four kinds |
| M3 | `check`: required sections + coverage matrix + citations + score points | 1 day | ✅ 8/8: positive case passes; missing section, insufficient coverage, missing answer, missing score point, empty citation, unfilled template and a section without a source are all rejected |
| M4 | Write-back: questions into the bank index; artifacts linked to the path | 0.5 day | ✅ 11/11: three bank rows with complete fields, re-runs add nothing, `link` writes `path.json`, `list` shows the linkage |
| M5 | Documentation and version 2.0.0, full regression | 0.5 day | ✅ 151 assertions green; README/TECH/VERSION updated; SKILL gained the five-step generation flow and trigger words |

**4 days total.** No milestone starts until the previous one passes.

---

## 4. Task breakdown

### M1 · artifacts skeleton

| ID | Task | Output | Acceptance |
|---|---|---|---|
| T1.1 | Define paths and naming for the four artifact kinds | Conventions written as code constants | Paths are predictable |
| T1.2 | Write 4 templates (pure skeletons with placeholders and required sections) | `templates/*.md` | Each marks its required sections |
| T1.3 | `artifacts.py new <type> --topic ...` | Generated file | All four kinds generate |
| T1.4 | `artifacts.py list` | List artifacts and status | Detects generated and missing ones |
| T1.5 | Tests: new + list | Test script | Passes |

### M2 · Input assembly (brief)

| ID | Task | Output | Acceptance |
|---|---|---|---|
| T2.1 | Define the brief structure (materials / mastery / errors / path / requirements) | Doc + constants | Structure is fixed |
| T2.2 | Reuse `retrieve.search` for material excerpts | Function | Returns paragraphs with sources |
| T2.3 | Reuse `practice` / `srs` for mastery and due items | Function | Data is correct |
| T2.4 | `brief.py exam|lesson|handout|curriculum` | CLI | Emits one `brief.md` |
| T2.5 | Tests: fixture course | Test | Brief contains all four kinds of information |

### M3 · Validator

| ID | Task | Rule | Acceptance |
|---|---|---|---|
| T3.1 | Required-section check | Sections declared by the template must exist and be non-empty | Missing section is an error |
| T3.2 | Coverage matrix check (exam) | Every knowledge point × question type in the blueprint appears in the questions | Coverage < 100% is an error |
| T3.3 | Citation check | Every handout/lesson section has at least one source marker | No citation is an error |
| T3.4 | Score-point check (exam) | Every question has at least one scoring point | Missing is an error |
| T3.5 | Exit-code contract | 0 pass / 1 fail / 2 usage error | Scriptable |
| T3.6 | Tests: one positive and five negatives | Test | Each negative is caught |

### M4 · Write-back

| ID | Task | Output | Acceptance |
|---|---|---|---|
| T4.1 | Extract exam questions into structured rows | `题库/index.jsonl` | Readable by `list` |
| T4.2 | Link lesson/curriculum to `path.json` | Field `artifact` | Visible through `path.py list` |
| T4.3 | Tests: generate → write back → read | Test | Closed loop |

### M5 · Close-out

| ID | Task | Output |
|---|---|---|
| T5.1 | README command table: add the four entries | Documentation |
| T5.2 | TECH module table and version history | Documentation |
| T5.3 | VERSION.json → 2.0.0 | File |
| T5.4 | Full regression | Record |

---

## 5. Roles

| Role | Responsibility |
|---|---|
| Main agent | Writes code, templates, tests; revises |
| Independent review subagent | Only checks at M3/M5 whether the validator really rejects the negatives; does not watch the generation process |
| User | Approves the plan; does not take part in technical judgement |

---

## 6. Acceptance summary

| Item | Pass line |
|---|---|
| `artifacts.py new` | All four kinds generate; files land on the agreed paths |
| `brief.py` | Output contains material excerpts with sources, mastery, errors, path position |
| `check` positive | A valid artifact exits 0 |
| `check` negatives | Missing section / insufficient coverage / no citation / no score point each exit 1 and name the location |
| Write-back | Visible through `list` after generation; linkable through `path.py list` |
| Regression | All pre-existing 102 tests green |

---

## 7. Risks

| Risk | Response |
|---|---|
| Templates turn into methodology (scope drift again) | Templates contain structure and placeholders only, no teaching advice |
| Validation too strict, false positives | Write positive and negative tests for every rule first |
| Artifact paths scatter | Path constants live at the top of `artifacts.py` |
| Scope creep | The change process in section 8 |

---

## 8. Change control

1. New ideas during the iteration go to the backlog only; they are not implemented.
2. Changing scope requires: state the reason → name the acceptance items affected → approval → edit this file → then start work.
3. "Added it on the way" is forbidden outright.

## 9. Backlog

| Idea | Reason |
|---|---|
| ~~Keep or drop the parsing layer~~ | Decided: keep it, positioned as a capability-indication layer |
| Bilingual artifact contract | Templates and the validator's section headings are Chinese literals. A non-Chinese user can still run the whole pipeline, but the skeleton comes out in Chinese. Fix = alias table in `artifacts.py` (`blueprint` → `命题蓝图`, `answer` → `答案`, …) plus English template variants, with tests for both languages. **Not started; waiting for approval.** |
| Embedding-based semantic search | Adds a dependency |
| Question-bank database | Files are enough |
| UI | Decided against |
| Methodology references | The user explicitly does not want them |

## 10. Files not to touch

```
mem.py · mastery.py · srs.py · practice.py · review.py
path.py (read-only) · retrieve.py (called only) · parsers.py (decided: keep) · adapters/
```

---

## 11. Changes after v2.0 was frozen (2026-11-27, released as 2.0.1)

Recorded here because the change process requires it. None of these touch `mem.py` / `mastery.py` / `srs.py` / `practice.py` / `review.py` / `path.py`.

| Change | Reason | Evidence |
|---|---|---|
| All repository documents rewritten in English | The pack is published on GitHub for international use | README / TECH / AGENTS / PLAN / ROADMAP / THIRD_PARTY_NOTICES / VERSION.json |
| Skill rewritten in English with bilingual trigger words | English users could not trigger it; Chinese words kept so existing usage still works | `SKILL.md`; `test_p3_rules.py` now asserts both languages |
| `references/` installed together with the skill | `SKILL.md` linked `references/layout.md`, which was never copied to the agent config directory — a dangling link | `install_adapters.py`; installed tree now has both files |
| `config.json` no longer stores `pack_root` / `scripts_dir` | Both were written at install time and **never read by any script**; each script locates the pack from `__file__`. The pack is relocatable, so recording a machine path was pure noise and leaked a local path into the repository | `setup_config.py`; config now `{v, default_workspace?}`; copying the pack to another directory and running it still works |
| Parsing layer rebuilt as an engine registry | The old code hardcoded a fixed chain (pymupdf → pdfplumber → pdftotext …). Requirement: use whatever the machine has, do not mandate specific tools | `parsers.py`: about 20 engines registered with probe + reader, built-in html / ipynb / epub, text sniffing, pandoc / LibreOffice as generic fallback; adding an engine is one entry |
| Scanned-page threshold lowered 50 → 20 characters per page | A short but text-based PDF was being sent to OCR and its text replaced by OCR output | `test_parsers_registry.py` case "pdf 引擎来自登记表" |
| PDF page rendering for OCR falls back to `pdftoppm` / `mutool` | OCR of scanned PDFs required PyMuPDF specifically | `_pdf_to_images()` |
| MIT `LICENSE` added | Repository publication | `LICENSE`, copyright Yu Liang |
| Fallback memory root removed | Requirement: memory is written **only** inside a course folder. The CLI used to fall back to `%LOCALAPPDATA%\StudyPack\记忆`, which silently collected data outside any course | `paths.py` (`try_resolve_root` / `resolve_root` / `require_root`); CLI now exits 2 with the reason, `probe.py` still runs anywhere |
| Artifact templates and validator made bilingual | A Chinese-only artifact contract made the pack useless to non-Chinese users | `templates/en/`, `ALIASES` in `artifacts.py`, bilingual answer labels (`答案:` / `Answer:`, `评分点:` / `Scoring:`), `new --lang`, workspace `lang` field |
| README rewritten as a bilingual document | Chinese readers and international readers should each get a complete document | `README.md` (Chinese half + English half) |

New tests: `test_parsers_registry.py` (18), `test_e2e_formats.py` (4), `test_bilingual_artifacts.py` (13), `test_path_guard.py` (8). Total 195, all green.
