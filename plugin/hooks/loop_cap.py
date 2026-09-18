#!/usr/bin/env python3
"""Hook A - loop cap + re-grounding.

prompt mode (UserPromptSubmit): one user prompt = one round. Round 1 records
  the session objective; from warnAt on, re-grounding text is injected.
pretool mode (PreToolUse): past maxRounds, every tool call is DENIED (exit 2)
  until the user runs /discipline-reset or starts a new session.
"""
import sys
import time
import lib

mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"


def main():
    cfg = lib.load_config()
    data = lib.read_stdin()
    lib.debug_dump(cfg, f"loop-{mode}", data)
    lib.CURRENT_EVENT[0] = "UserPromptSubmit" if mode == "prompt" else "PreToolUse"

    sid = str(lib.first_of(data, "session_id", "sessionId", "sessionID", default="default"))
    st = lib.load_state()
    sessions = st.setdefault("sessions", {})
    s = sessions.setdefault(sid, {"rounds": 0, "objective": "", "updated": 0})

    max_rounds = int(cfg.get("maxRounds", 15))
    warn_at = int(cfg.get("warnAt", max(1, max_rounds - 3)))

    if mode == "prompt":
        prompt = str(lib.first_of(data, "prompt", "userPrompt", "text", default="")).strip()
        if s["rounds"] == 0 or not s["objective"]:
            s["objective"] = prompt[:2000]
            s["rounds"] = 1
            lib.log(f"[{sid}] round 1 objective recorded")
        else:
            s["rounds"] += 1
        s["updated"] = time.time()
        lib.save_state(st)
        r = s["rounds"]
        lib.log(f"[{sid}] round {r}/{max_rounds}")
        if r == warn_at:
            lib.emit_context(
                f"DISCIPLINE WARNING: round {r} of {max_rounds} for this session. "
                f"Objective: {s['objective'][:500]} — finish or converge NOW; "
                f"at {max_rounds} all tool calls are denied.")
        elif r > warn_at:
            lib.emit_context(
                f"DISCIPLINE: round {r}/{max_rounds}. Objective: {s['objective'][:500]} — "
                f"no adjacent work, converge or report.")
        return

    # pretool mode
    if s["rounds"] > max_rounds:
        lib.log(f"[{sid}] DENY tool call, cap {max_rounds} reached")
        print("discipline: loop cap %d reached for this session — finish and report "
              "to the user; they can continue with /discipline-reset" % max_rounds,
              file=sys.stderr)
        sys.exit(2)


try:
    main()
except SystemExit:
    raise
except Exception as e:
    lib.log(f"loop_cap internal error: {e!r}")
    sys.exit(0)
