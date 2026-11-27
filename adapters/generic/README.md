# Generic usage (any agent that can run commands)

If your agent supports neither hooks nor MCP, call the scripts by hand. Three commands are enough.

## Run from inside the course folder

```powershell
cd D:\courses\calculus
```

The folder must contain `.study-workspace` — a one-line marker you write yourself (the plugin does not create courses). With that file present, the scripts write into `calculus\记忆\`.

```json
{"v":1,"name":"calculus"}
```

## The three commands

**Search the materials**

```powershell
python <PACK>\core\scripts\retrieve.py search "chain rule"
```

**Record one answer**

```powershell
python <PACK>\core\scripts\practice.py record --kp "chain rule" --type procedure --result 1
```

**See mastery**

```powershell
python <PACK>\core\scripts\practice.py list
```

## If your agent reads a project instruction file

Put the lines below into the course folder's `AGENTS.md` (or `CLAUDE.md`) and the agent will know how to cooperate:

```markdown
# Learning workspace

When answering a question about the materials, search first with retrieve.py and cite the source; if nothing matches, say so.
- Search: python <PACK>/core/scripts/retrieve.py search "<keywords>"
- Grade:  python <PACK>/core/scripts/practice.py record --kp "<knowledge point>" --type <type> --result <0|1>
```

Replace `<PACK>` with the absolute path of this pack. The installer does that substitution for the OpenCode adapter automatically; for a hand-written `AGENTS.md` you do it once yourself.
