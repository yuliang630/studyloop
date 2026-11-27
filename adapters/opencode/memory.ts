// @studyloop-managed
/**
 * memory —— 学习插件 · OpenCode 薄适配器
 *
 * 只做三件事，不含业务逻辑：
 *   1. idle    → 取 session.context，交给 mem.py ingest 追加 L1（并顺手刷新注入缓存）
 *   2. context → 读缓存，splice 进 system
 *
 * 记忆根按「会话」解析，且**只在课程工作区里记**：
 *   session.get(sid).location.directory 下有 .study-workspace → <该目录>/记忆
 *   否则 → 一律不写（B 方案：学习插件只管课程，不建全局兜底库）
 *
 * 降级策略（不静默）：找不到 python / mem.py 时写日志并停用，不影响对话本身。
 */

const PACK_ROOT = "__PACK_ROOT__"
const SCRIPTS = process.env.MEMORY_SCRIPTS ?? `${PACK_ROOT}/core/scripts`
const PYTHON = process.env.MEMORY_PYTHON ?? "python"
const MARKER_FILE = ".study-workspace"
const MARKER = "【记忆库·自动注入】"
const SKIP_LOG = `${process.env.TEMP ?? "."}/study-hook-skip.log`

let FS: typeof import("node:fs") | null = null
let EXEC: typeof import("node:child_process") | null = null

let DEFAULT_ROOT: string | null = null
const rootBySession = new Map<string, string>()   // 只存"已确认是课程"的会话
const skipped = new Set<string>()                 // 已确认"不是课程"的会话

type AnyRecord = Record<string, unknown>
type HookRegistrar = (name: string, cb: (event: unknown) => unknown, options?: unknown) => Promise<unknown>
type SessionApi = {
  hook?: HookRegistrar
  context?: (input: { sessionID: string }) => Promise<unknown>
  get?: (input: { sessionID: string }) => Promise<unknown>
}

const g = globalThis as unknown as { __memQueue?: Promise<unknown> }

function enqueue(task: () => Promise<void>): void {
  const prev = g.__memQueue ?? Promise.resolve()
  g.__memQueue = prev.then(task).catch((err) => void log("queue failed " + String(err)))
}

/** 写日志：有课程根就写课程内，没有就写临时目录的 skip 日志。 */
async function log(line: string, root: string | null = DEFAULT_ROOT): Promise<void> {
  try {
    const fs = await import("node:fs")
    const file = root ? `${root}/data/state/memory-hook.log` : SKIP_LOG
    if (root) fs.mkdirSync(`${root}/data/state`, { recursive: true })
    fs.appendFileSync(file, `${new Date().toISOString()} ${line.replace(/\r?\n/g, " ").slice(0, 800)}\n`, "utf8")
  } catch {
    /* 日志失败不影响主流程 */
  }
}

function runMem(root: string, args: string[], input?: string): { ok: boolean; out: string } {
  if (!EXEC) return { ok: false, out: "child_process 未加载" }
  try {
    const out = EXEC.execFileSync(PYTHON, [`${SCRIPTS}/mem.py`, ...args], {
      input,
      encoding: "utf8",
      timeout: 20000,
      windowsHide: true,
      env: {
        ...process.env,
        MEMORY_ROOT: root,
        PYTHONIOENCODING: "utf-8",
        MEM_CONSOLE_PROBE: "1",
      },
      stdio: ["pipe", "pipe", "pipe"],
    })
    return { ok: true, out: String(out).trim() }
  } catch (err) {
    const e = err as { stderr?: unknown; message?: unknown }
    return { ok: false, out: String(e?.stderr ?? e?.message ?? err).slice(0, 400) }
  }
}

function isWorkspace(dir?: string): boolean {
  if (!dir || !FS) return false
  try {
    return FS.existsSync(`${dir}/${MARKER_FILE}`)
  } catch {
    return false
  }
}

/** 解析会话的记忆根；不是课程工作区就返回 null（B 方案：不写兜底库）。 */
async function rootFor(session: SessionApi | undefined, sid: string): Promise<string | null> {
  const cached = rootBySession.get(sid)
  if (cached) return cached
  if (skipped.has(sid)) return null

  const envRoot = process.env.MEMORY_ROOT
  if (envRoot) {
    rootBySession.set(sid, envRoot)
    return envRoot
  }

  if (session?.get) {
    try {
      const meta = (await session.get({ sessionID: sid })) as AnyRecord | undefined
      const loc = (meta?.location ?? {}) as AnyRecord
      const dir = typeof loc.directory === "string" ? loc.directory : ""
      if (isWorkspace(dir)) {
        const root = `${dir}/记忆`
        rootBySession.set(sid, root)
        return root
      }
      // 明确查到"不是课程目录" → 不写
      skipped.add(sid)
      return null
    } catch {
      /* 查询失败，走下面的兜底 */
    }
  } else if (DEFAULT_ROOT) {
    // 没有 session.get（或本实例已确认处于课程工作区）→ 用本实例的工作区
    rootBySession.set(sid, DEFAULT_ROOT)
    return DEFAULT_ROOT
  }

  skipped.add(sid)
  return null
}

function stripOldInjection(system: unknown[]): void {
  for (let i = system.length - 1; i >= 0; i--) {
    const part = system[i] as AnyRecord | string
    const text = typeof part === "string" ? part : String((part as AnyRecord)?.text ?? "")
    if (text.includes(MARKER)) system.splice(i, 1)
  }
}

function refreshCacheIfStale(root: string): void {
  if (!FS) return
  const cache = `${root}/data/state/inject-cache.md`
  try {
    let newest = 0
    for (const p of [
      `${root}/data/L3/default/profile.md`,
      `${root}/data/L3/default/recent.md`,
      `${root}/data/state/path.json`,
      `${root}/data/state/reviews.json`,
    ]) {
      try {
        newest = Math.max(newest, FS.statSync(p).mtimeMs)
      } catch {
        /* 不存在 */
      }
    }
    let cacheMtime = 0
    if (FS.existsSync(cache)) cacheMtime = FS.statSync(cache).mtimeMs
    if (newest > cacheMtime) {
      const res = runMem(root, ["inject", "--out", cache])
      void log(res.ok ? "inject: cache rebuilt" : "inject: cache rebuild FAILED " + res.out, root)
    }
  } catch {
    /* ignore */
  }
}

export default {
  id: "memory",

  async setup(ctx: { session?: SessionApi; location?: { directory?: string } }) {
    FS = await import("node:fs")
    EXEC = await import("node:child_process")

    const dir = ctx?.location?.directory
    DEFAULT_ROOT = process.env.MEMORY_ROOT ?? (isWorkspace(dir) ? `${dir}/记忆` : null)

    await log(
      `setup: entered root=${DEFAULT_ROOT ?? "(非课程，不记录)"} workspace=${dir ?? "?"} scripts=${SCRIPTS}`,
    )

    const session = ctx?.session
    const register = session?.hook
    if (typeof register !== "function") {
      await log("setup: session.hook 不可用，插件停用")
      return
    }

    // ---------------- 注入 ----------------
    try {
      await register("context", (event: unknown) => {
        const e = (event ?? {}) as AnyRecord & { system?: unknown[] }
        const system = e.system
        if (!Array.isArray(system) || !FS) return
        stripOldInjection(system)

        const sid = typeof e.sessionID === "string" ? e.sessionID : ""
        const root = sid ? rootBySession.get(sid) ?? DEFAULT_ROOT : DEFAULT_ROOT
        if (!root) return

        try {
          refreshCacheIfStale(root)
          const cache = `${root}/data/state/inject-cache.md`
          if (!FS.existsSync(cache)) return
          const block = FS.readFileSync(cache, "utf8").trim()
          if (!block) return
          system.splice(1, 0, { type: "text", text: block })
          void log(`inject: ok chars=${block.length}`, root)
        } catch (err) {
          void log("inject: failed " + String(err), root)
        }
      })
      await log("register context: ACCEPTED")
    } catch (err) {
      await log("register context: THREW " + String(err))
    }

    // ---------------- 写回 ----------------
    try {
      await register("experimental.idle", (event: unknown) => {
        let sid = ""
        try {
          const e = (event ?? {}) as AnyRecord
          sid = typeof e.sessionID === "string" ? e.sessionID : ""
        } catch {
          /* ignore */
        }
        if (!sid) return
        enqueue(async () => {
          const root = await rootFor(session, sid)
          if (!root) {
            await log(`idle: 非课程工作区，跳过 sid=${sid}`, null)
            return
          }
          const contextFn = session?.context
          if (typeof contextFn !== "function") {
            await log("idle: session.context 缺失，跳过 " + sid, root)
            return
          }
          let items: unknown = null
          try {
            items = await contextFn({ sessionID: sid })
          } catch (err) {
            await log("idle: context 调用失败 " + String(err), root)
            return
          }
          if (!Array.isArray(items) || items.length === 0) return

          const payload = JSON.stringify(items)
          const cacheFile = `${root}/data/state/inject-cache.md`
          const res = runMem(
            root,
            ["ingest", "--from-stdin", "--sid", sid, "--refresh-out", cacheFile],
            payload,
          )
          await log(`idle: ingest ${res.ok ? "OK" : "FAILED"} root=${root} ${res.out.slice(0, 300)}`, root)

          // 心跳：只有真的写入 L1 才更新，供 mem.py boot 判断"钩子在不在工作"
          if (res.ok && /\[ok\] 写入 L1/.test(res.out)) {
            try {
              if (FS) {
                const hbFile = `${root}/data/state/hook.json`
                let prev: Record<string, unknown> = {}
                try {
                  prev = JSON.parse(FS.readFileSync(hbFile, "utf8")) as Record<string, unknown>
                } catch {
                  /* 第一次运行，没有旧心跳 */
                }
                const turns = Number(prev.turns ?? 0) + 1
                FS.writeFileSync(
                  hbFile,
                  JSON.stringify({ v: 1, last_ingest_at: new Date().toISOString(), turns, surface: "hook" }, null, 2),
                  "utf8",
                )
              }
            } catch {
              /* 心跳写不了不影响记录本身 */
            }
          }

          if (!res.ok) {
            try {
              if (FS) FS.writeFileSync(`${root}/data/state/last-ingest-payload.json`, payload, "utf8")
            } catch {
              /* ignore */
            }
          }
        })
        return undefined
      })
      await log("register experimental.idle: ACCEPTED")
    } catch (err) {
      await log("register experimental.idle: THREW " + String(err))
    }

    await log("setup: done")
  },
}
