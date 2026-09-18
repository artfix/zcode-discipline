---
description: Reset the discipline loop-cap counter for this session
---

Reset the zcode-discipline round counter so tool calls are allowed again.

Run exactly this bash command and report its output:

```bash
python3 -c "
import json, pathlib, sys
f = pathlib.Path.home() / '.zcode/discipline-state/state.json'
try:
    st = json.loads(f.read_text())
except Exception:
    print('no state file - nothing to reset'); sys.exit(0)
st.get('sessions', {}).clear()
st.get('stopBlocks', {}).clear()
tmp = f.with_suffix('.json.tmp'); tmp.write_text(json.dumps(st, indent=1)); tmp.replace(f)
print('loop cap reset - all sessions back to round 0')
"
```

Then confirm to the user in one line.
