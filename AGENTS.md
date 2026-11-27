# AGENTS.md · Guide for the agent that picks this pack up

You are probably here to **install it on this machine** or **migrate it to another one**. Follow the order below; do not skip steps.

---

## 1. Can it run here? (30 seconds)

```powershell
python -V
```

- Version **≥ 3.11** → continue
- No Python, or too old → tell the user to install Python (with "Add to PATH"). **Do not download or install it yourself.**
- Not Windows → this version does not support it; say so plainly.

---

## 2. Install on this machine (three steps)

```powershell
cd <pack-directory>
python core\scripts\setup_config.py              # optional local preferences (no machine paths)
python core\scripts\install_adapters.py --discover   # what skill directories exist here?
python core\scripts\install_adapters.py --skills-dir <one of them>
```

`install_adapters.py` rules — do not work around them:

1. **There is no agent list in the code.** The destination is a directory, so any host works. Never add an enum of agent names back.
2. No `--skills-dir`, no `STUDYLOOP_SKILLS_DIR`, and not exactly one discovered candidate → it prints instructions and writes nothing.
3. It never creates a target directory; a missing path is an error (exit 2).
4. It never overwrites a file it does not own: the target must contain `@studyloop-managed`, otherwise it reports a conflict and exits **3**. `--force` overwrites but saves `<name>.bak-<timestamp>` first.
5. Hooks are optional and host-specific: `--plugin-dir <dir>` drops the hook file, `--hook-json` prints a `settings.json` snippet to merge by hand. Skills alone work without any hook.

**Restart the agent afterwards** (only if a hook was installed), otherwise hooks will not load.

Upgrading from 2.0.x: the old installer wrote no ownership marker, so the first run reports a conflict and exits 3. After confirming those files are the ones this pack installed, run once with `--force`; each file is backed up first.

Without OpenCode: use `adapters\claude-code\hooks.json` (merge into `settings.json` manually), or run the command line directly (`adapters\generic\README.md`).

---

## 3. Migrate to another machine

### Case A: program only (fresh start)

Copy the whole `studyloop\` directory, then run the three steps above.

### Case B: include learning records

1. Copy `studyloop\`
2. Copy each course folder (**must include `记忆\` and `.study-workspace`**)
3. Run the three steps on the new machine
4. Open the course folder with the agent, then run `python core\scripts\probe.py` and confirm `source` shows `workspace:.study-workspace`

### Three post-migration checks

| Check | Command | Expected |
|---|---|---|
| memory root points at the course | `probe.py` | `source workspace:...` |
| record count matches | `mem.py stats` | same as the old machine |
| retrieval works | `retrieve.py search "any word"` | hits, or an explicit "no match" |

---

## 4. Hard constraints (violating these destroys data)

1. **Never hand-edit files under `记忆\data\`**; delete through `mem.py forget` (it archives first).
2. **Never write memory outside a course**: only directories containing `.study-workspace` count. There is no fallback root — the CLI exits 2 with the reason, and `probe.py` reports "not located". Options are explicit: `MEMORY_ROOT`, or `setup_config.py --workspace`.
3. **Never overwrite the user's existing `AGENTS.md`**: append learning rules, do not replace. The plugin does not create courses or course directories.
4. **Never change grading rules without running the tests**: `test_mastery.py` is the only guard against grading drift.
5. **Never make a third-party library required by `retrieve.py`**: optional engines only, with graceful degradation. The pack's lifeline is "Python and nothing else".
6. **Never touch the user's course content** (materials, notes, experiments) unless explicitly asked.

---

## 5. Post-install self-check (all four must pass)

```powershell
python core\scripts\probe.py                      # environment sane, route clear
python core\scripts\mem.py stats                  # data readable (0 is fine on a new machine)
python core\scripts\retrieve.py stats             # index present, or a hint to build it
python core\scripts\practice.py list              # no crash when empty
```

Real-machine verification (with an agent):

1. Open a course folder with the agent and say one sentence
2. Check `<course>\记忆\data\state\memory-hook.log` for `idle: ingest OK`
3. Check that `L1\` gained exactly one record

---

## 6. File map

| Path | What it is |
|---|---|
| `README.md` | user-facing documentation (install, usage) |
| `TECH.md` | developer documentation (architecture, contracts, how to change) |
| `VERSION.json` | machine-readable manifest |
| `THIRD_PARTY_NOTICES.md` | algorithm and third-party attribution |
| `core\scripts\paths.py` | **the only place that resolves paths** — read this first |
| `core\scripts\mem.py` | memory read/write; the largest file |
| `core\scripts\parsers.py` | material parsing: engine registry (probe + reader per engine), per-format chains, generic fallback; **missing engines are skipped, never fatal** |
| `core\scripts\artifacts.py` | artifact scaffolding, validation, question bank, path linkage; templates in `templates\` (zh) and `templates\en\` (en) |
| `core\scripts\brief.py` | assembles the input packet for artifact generation |
| `adapters\opencode\memory.ts` | the only hook-based adapter (thin shell, about 250 lines) |
| `<course>\记忆\data\state\` | runtime state (cursors, attempts, reviews, index) |

---

## 7. Where to look when something breaks

| Symptom | Check first |
|---|---|
| No memory | `memory-hook.log` for `非课程工作区，跳过` or the `setup` line |
| Memory from one course appearing in another | the `root=` value in the log vs. the current course path |
| Flashing console windows | the plugin must carry `windowsHide`; `MEMORY_PYTHON` should point at the real `python.exe` |
| Retrieval returns nothing | `retrieve.py stats` for chunk count; check `sources` in `.study-workspace` |
| Mastery never moves | new rows in `attempts.jsonl`; `--hints` greater than 0 is not counted as evidence |
| Every command exits 2 with "not a course workspace" | you are not inside a course folder. `cd` into the folder containing `.study-workspace`, or set `MEMORY_ROOT` explicitly. This is by design — there is no fallback root |
| Artifact lands in the wrong place | `artifacts.py layout` for the effective layout; override via `layout` in `.study-workspace` |
