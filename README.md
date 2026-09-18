# zcode-discipline

Discipline hooks for ZCode: keeps agent sessions on-mission, forces proof
before "done", and backs up the session DB.

Three independent hooks (all fail-open — a plugin bug can never block your
work; only deliberate gates exit-block):

| Hook | Fires on | Does |
|---|---|---|
| **Loop cap** | UserPromptSubmit, PreToolUse | Counts rounds per session (1 round = 1 prompt). Round 1 records the objective. From `warnAt` it injects re-grounding text each round; past `maxRounds` it **denies all tool calls** until `/discipline-reset`. |
| **Verification** | PostToolUse (Edit\|Write), Stop | Reads every edited file back (did it land?). On Stop: unverified edits veto the stop — model must run `verifyCommand` or explain — max 3 vetoes (ZCode-native cap), then it may stop. |
| **Backup** | SessionStart (startup only) | Consistent sqlite snapshot of `~/.zcode/cli/db/db.sqlite` (WAL-safe), gzipped, keep-N rotation. |

## Install

From this directory (local marketplace): Settings → Plugin Management →
Discover → `+` → select this folder → install **zcode-discipline**.

From GitHub (after push): Discover → `+` → paste the repo URL → install.

## Configuration

`~/.zcode/discipline-state/config.json` (created on first fire; defaults):

```json
{
  "debug": true,               // dump raw hook input to debug/ (flip off after first session)
  "maxRounds": 15,             // tool-deny cap per session
  "warnAt": 12,                // re-grounding starts here
  "stopGate": "soft",          // off | soft (veto only if verifyCommand set) | hard (veto on any unverified edit)
  "verifyCommand": "",         // e.g. "npm test" - run from the project dir at Stop
  "backups": { "keep": 5, "maxSourceMB": 500 }
}
```

## Commands

- `/discipline-reset` — zero the round counter, tools allowed again
- `/discipline-status` — plain-language state summary
- `/discipline-verify` — run verifyCommand now, record the proof

## State & logs

Everything lives under `~/.zcode/discipline-state/`:
`state.json` (rounds/markers), `discipline.log` (1MB self-rotating),
`backups/`, `debug/` (raw hook input while `debug: true`).

## Uninstall

Settings → Plugin Management → Installed → toggle off (hooks vanish
immediately) or uninstall. Optionally delete `~/.zcode/discipline-state/`.

## Notes

- The re-grounding injection uses the Claude-compatible
  `hookSpecificOutput.additionalContext` shape; if ZCode's strict schema
  rejects it, the only effect is a note in the ZCode log — fix the shape in
  `lib.emit_context` once the live dump confirms the expected key.
- Hook runs (fired/blocked/failed) are recorded in ZCode's own log with
  source and duration.
