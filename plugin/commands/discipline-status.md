---
description: Show discipline plugin state (rounds, objective, unverified edits)
---

Show the user the current zcode-discipline state. Read these two files and
summarize them in a small plain-language table (no JSON dump):

- ~/.zcode/discipline-state/state.json
- ~/.zcode/discipline-state/config.json

Then run this helper to get the session names the ZCode UI shows (read-only
lookup in the client DB) and use them as row labels instead of raw UUIDs —
fall back to the short UUID when a session has no title. The version dir in
the cache changes on every reinstall, so glob for it:

```bash
python3 "$(ls -d ~/.zcode/cli/plugins/cache/john-zcode-plugins/zcode-discipline/*/hooks/titles.py 2>/dev/null | tail -1)"
```

Report: for each session — current round / max, recorded objective, unverified
edits, stop-blocks used; then the configured knobs (maxRounds, warnAt,
stopGate, verifyCommand, backup keep). If files are missing, say the plugin
has no state yet.
