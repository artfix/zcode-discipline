#!/usr/bin/env python3
"""Hook A - loop cap + re-grounding. Contract: see lib.py docstring.

prompt mode (UserPromptSubmit): 1 user prompt = 1 round; round 1 records the
  objective; from warnAt injects re-grounding via hookSpecificOutput.
pretool mode (PreToolUse): past maxRounds denies via permissionDecision=deny.
"""
import sys
import time

import lib

mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"


def main():
    cfg = lib.load_config()
    data = lib.read_stdin()
    lib.debug_dump(cfg, f"loop-{mode}", data)

    event = data.get("hook_event_name") or data.get("hookEventName") or ""
    sid = data.get("session_id") or data.get("sessionId") or "default"
    st = lib.load_state()
    sessions = st.setdefault("sessions", {})
    s = sessions.setdefault(str(sid), {"rounds": 0, "objective": "", "updated": 0})

    max_rounds = int(cfg.get("maxRounds", 15))
    warn_at = int(cfg.get("warnAt", max(1, max_rounds - 3)))

    if mode == "prompt":
        prompt = str(data.get("prompt") or "").strip()
        if s["rounds"] == 0 or not s["objective"]:
            s["objective"] = prompt[:2000]
            s["rounds"] = 1
            lib.log(f"[{sid}] round 1 objective recorded")
        else:
            s["rounds"] += 1
        s["updated"] = time.time()
        lib.save_state(st)
        r = s["rounds"]
        lib.log(f"[{sid}] round {r}/{max_rounds} ({event})")
        if r == warn_at:
            lib.emit_context(event,
                f"DISCIPLINE WARNING: round {r} of {max_rounds} for this session. "
                f"Objective: {s['objective'][:500]} — finish or converge NOW; "
                f"at {max_rounds} all tool calls are denied.")
        elif r > warn_at:
            lib.emit_context(event,
                f"DISCIPLINE: round {r}/{max_rounds}. Objective: {s['objective'][:500]} — "
                f"no adjacent work, converge or report.")
        return

    # pretool mode
    if s["rounds"] > max_rounds:
        lib.log(f"[{sid}] DENY tool call, cap {max_rounds} reached")
        lib.deny_tool(
            f"discipline: loop cap {max_rounds} reached for this session — "
            f"finish and report to the user; they can continue with /discipline-reset")


try:
    main()
except SystemExit:
    raise
except Exception as e:
    lib.log(f"loop_cap internal error: {e!r}")
    sys.exit(0)
