---
description: Show discipline plugin state (rounds, objective, unverified edits)
---

Show the user the current zcode-discipline state. Read these two files and
summarize them in a small plain-language table (no JSON dump):

- ~/.zcode/discipline-state/state.json
- ~/.zcode/discipline-state/config.json

Report: for each session — current round / max, recorded objective, unverified
edits, stop-blocks used; then the configured knobs (maxRounds, warnAt,
stopGate, verifyCommand, backup keep). If files are missing, say the plugin
has no state yet.
