# zcode-discipline

A ZCode plugin that keeps agent sessions on a leash. Install it, open a new
session, and it just works — **no configuration needed**. Everything below is
optional tuning.

---

## What it does for you (human version)

You know how an agent session can go wrong in three classic ways? It wanders
off your goal, it says "done" when nothing works, or a corrupted session DB
eats your history. This plugin catches all three.

**1. It stops runaway sessions.**
Every message you send counts as a "round". The agent has 15 rounds of full
power. From round 12 it gets a growing reminder of what your original request
was, so it stops drifting into random side-work. At the cap it loses its
hands — every tool call is refused — and it must report back to you instead of
churning forever; the cap notice appears once, then the session stays quiet.
You can always let it continue: type `/discipline-reset` — that command and
status checks work even while capped.

**2. It catches phantom edits.**
After the agent edits or writes any file, the plugin opens that file back up
and checks the change actually landed on disk. If it didn't, the agent is told
immediately and redoes it — instead of building the next ten steps on a file
that was never written.

**3. It won't accept "done" without proof (optional).**
Here is the only decision in the whole plugin, and you can ignore it forever:
how does the agent *prove* its work actually functions? The answer is one
command — for example `npm test` for a project with tests, or
`curl -s localhost:8000` to check a server is alive. If you set that one line,
the plugin refuses the agent's "I'm finished" while the command fails, and
feeds the error back so the agent fixes it. **If you never set it, this guard
stays completely quiet** — the plugin never nags you about it.

**4. It backs up your session database.**
Every time a new ZCode session starts, the plugin takes a safe snapshot of
your session database (`~/.zcode/cli/db/db.sqlite`) and keeps the last 5
copies, compressed. A crash or corruption can never again wipe your session
history — restore is a copy back.

**What you'll actually see in daily use:** nothing, 99% of the time. The
nudges and the cap only appear when a session really is running long, the
edit-checks are invisible unless something went wrong, and backups are one
small file per session start. If the cap ever trips on a task that genuinely
needed more rounds, `/discipline-reset` and carry on.

---

## The three commands

| Command | What it does |
|---|---|
| `/discipline-reset` | Zeroes the round counter — tool calls allowed again (whitelisted, works even while capped) |
| `/discipline-status` | Shows you where every session stands, in plain words, named like the UI shows them |
| `/discipline-verify` | Runs your proof command right now and shows pass/fail |

---

## Install

**Local folder:** Settings → Plugin Management → **Discover** → **`+`** →
select this folder → install **zcode-discipline**.

**From GitHub:** push this repo, then Discover → **`+`** → paste the repo URL
→ install. Same plugin either way.

Hooks load in **new sessions only** — restart or open a fresh session after
installing.

**Uninstall:** toggle it off in Settings → Plugin Management. Hooks load per
session, so a session that is already running keeps firing them until you
restart it or open a fresh one (observed 2026-09-19 — the toggle is not
instant in live sessions). Optionally delete `~/.zcode/discipline-state/`.

---

## Technical reference

### Hooks (7 ZCode events used, scripts are python3, no shell)

| Hook | Event / matcher | Script | Effect |
|---|---|---|---|
| Loop cap | `UserPromptSubmit` | `loop_cap.py prompt` | Round counter; first non-junk prompt records the objective (greetings/keyboard mash skipped); from `warnAt` injects re-grounding; at the cap injects once, then stays silent |
| Loop cap | `PreToolUse` (all tools) | `loop_cap.py pretool` | At `maxRounds`: JSON-deny every tool call except `/discipline-reset`'s bash command and reads of `discipline-state` files |
| Verification | `PostToolUse` on `Edit\|Write` | `verify.py posttool` | Read-back check (file exists, non-empty); failure → `additionalContext` to the model; records unverified marker |
| Verification | `Stop` (all) | `verify.py stop` | Unverified edits → `continue: false` veto with reason, max 3 (matches ZCode's continuation cap); `verifyCommand` exit 0 clears the marker |
| Backup | `SessionStart` on `startup` | `backup.py session-start` | sqlite3 backup API (WAL-safe, read-only source) → gzip → rotate keep-N |

### Failure philosophy

- **Fail-open, learned the hard way (v0.3.1):** every hook catches
  `BaseException` — including `SystemExit`, which is exactly how v0.3.0's
  argparse crash escaped the old guard, exited 2, and made ZCode block every
  prompt (the plugin literally made the agent untalkable-to). Now a hook
  cannot exit nonzero even if it tries. The only blocking paths are the two
  deliberate gates (loop cap deny, stop veto), emitted as verified JSON at
  exit 0.
- **Strict output schema:** hooks emit ONLY keys verified against ZCode's
  core output schema (`AJt`): `continue`, `decision`, `reason`, `stopReason`,
  `suppressOutput`, `systemMessage`, `additionalContext`, and
  `hookSpecificOutput` (per-event union, `hookEventName` required inside).
  Deny = `permissionDecision: "deny"` (PreToolUse union member); stop veto =
  `continue: false` + `stopReason`. One unknown key would discard the whole
  output — hence none are emitted.
- **No daemons:** hooks run only on their events (worst case the backup,
  ~1.5s for a 79MB DB). Everything else is milliseconds.

### State — everything under `~/.zcode/discipline-state/`

| Path | Contents |
|---|---|
| `state.json` | Per-session rounds, objectives, unverified-edit markers, stop-block counts |
| `config.json` | ALL knobs live here (see table below) — this is the one source of truth |
| `discipline.log` | Human-readable activity log, self-rotates at 1MB |
| `backups/` | `db-<timestamp>.sqlite.gz`, keep 5 |
| `debug/` | Raw hook input dumps while `debug: true` — read one after the first live session, then set `debug: false` |

### Settings — one file: `~/.zcode/discipline-state/config.json` (v0.3.1+)

v0.3.0 declared the knobs as `userConfig` and passed them via
`${user_config.*}` expansion in `hooks.json`. **That was wrong: ZCode expands
`${ZCODE_PLUGIN_ROOT}` but does NOT expand `${user_config.*}` in hook args —
the hooks received the literal placeholder strings, argparse died on them, and
the nonzero exit made ZCode block every prompt (the plugin became a wall you
could not talk through). v0.3.1 removes all of that machinery.**

The hooks now read every knob from `~/.zcode/discipline-state/config.json`,
falling back to the manifest defaults. This also fixed the "proof command with
spaces" worry: `verifyCommand` reaches the hook as one JSON value, never
through shell argument splitting.

```json
{
  "debug": false,
  "maxRounds": 15,
  "warnAt": 12,
  "stopGate": "soft",
  "verifyCommand": "npm test",
  "backups": { "keep": 5, "maxSourceMB": 500 }
}
```

| Key | Default | Meaning |
|---|---|---|
| `maxRounds` | `15` | Prompts per session before tool calls are denied |
| `warnAt` | `12` | Round where re-grounding nudges start (auto-clamped below max) |
| `stopGate` | `soft` | `off` = never veto stops · `soft` = veto only if a proof command is set · `hard` = veto any unverified edit |
| `verifyCommand` | `""` | Proof command run at Stop and `/discipline-verify`, from the project dir — spaces fine |
| `backups.keep` | `5` | How many DB snapshots to keep |
| `backups.maxSourceMB` | `500` | Skip backup if the DB grows past this |
| `debug` | `true` | Dumps raw hook input to `debug/` — set `false` after the first session confirmed the payload shape |

The manifest keeps a `userConfig` block so the settings UI still *shows* the
knobs, but in the current client the UI does not persist values anywhere the
hooks can read (verified: no such file exists on disk). Treat `config.json`
as the only way to change settings.

### The one manual thing, explained

The plugin cannot know what "works" means for *your* project — only you know
whether proof is a test suite, a running server, or nothing at all. That is
the entire reason `verifyCommand` exists and the only reason any manual step
could ever be involved. Leave it `""` and `stopGate` `soft`: the plugin still
does everything else, silently.

### Hook contract (verified against ZCode core code)

Input (snake_case, built by ZCode's Claude-compat layer): `session_id`,
`hook_event_name`, `permission_mode`, `agent_type`, `cwd`, `timestamp`,
`transcript_path`; per event: `prompt` (UserPromptSubmit),
`tool_name`/`tool_input`/`tool_use_id` (Pre/PostToolUse), `tool_response`
(PostToolUse), `stopHookActive`/`responseText`/`toolCallCount` (Stop).

Output: the strict top-level schema listed above; `hookSpecificOutput` is a
discriminated union on `hookEventName` — PreToolUse accepts
`permissionDecision` (allow/ask/deny) + `permissionDecisionReason`; all other
events accept `additionalContext`.

## License

MIT
