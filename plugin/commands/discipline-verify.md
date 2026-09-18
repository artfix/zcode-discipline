---
description: Run the configured verification command and record the proof
---

Run the verification proof for this session.

1. Read ~/.zcode/discipline-state/config.json and get "verifyCommand".
2. If it is empty: tell the user no verify command is configured, and where to
   set one (that config file, key verifyCommand). Stop there.
3. Otherwise run it in the current project directory (shell), capture the exit
   code and the last ~20 lines of output.
4. Report pass/fail plainly with the output tail.
5. On PASS, clear the session's unverified marker so the stop-gate allows
   stopping:

```bash
python3 -c "
import json, pathlib
f = pathlib.Path.home() / '.zcode/discipline-state/state.json'
try: st = json.loads(f.read_text())
except Exception: raise SystemExit(0)
st.get('unverified', {}).clear()
tmp = f.with_suffix('.json.tmp'); tmp.write_text(json.dumps(st, indent=1)); tmp.replace(f)
print('unverified markers cleared - stop gate open')
"
```
