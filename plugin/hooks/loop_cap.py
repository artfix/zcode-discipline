#!/usr/bin/env python3
"""Hook A - loop cap + re-grounding. Contract: see lib.py docstring.

prompt mode (UserPromptSubmit): 1 user prompt = 1 round; the objective is
  recorded from the first non-junk prompt (bare greetings and keyboard mash
  are skipped, not stored); from warnAt injects re-grounding via
  hookSpecificOutput. At the cap the notice is injected ONCE, then the hook
  stays silent on later prompts (tools are denied with the same info anyway).
pretool mode (PreToolUse): past maxRounds denies via permissionDecision=deny,
  EXCEPT the escape hatch: /discipline-reset's bash command and read-only
  access to ~/.zcode/discipline-state/ files (status must work at cap —
  v0.2.0 blocked its own reset, a catch-22).
"""
import re
import sys
import time

import lib

mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"

# /discipline-reset runs this script via Bash; both markers must appear, so a
# stray shell command can't pass as the reset.
RESET_MARKERS = ("discipline-state/state.json", "loop cap reset")
READ_TOOLS = {"Read", "Grep", "Glob"}


def knobs(cfg):
    """Knobs come from config.json over lib defaults. No argparse and no
    ${user_config.*} args: ZCode does not expand those placeholders (verified
    0.3.0 — argparse got the literal string and its SystemExit(2) exit code
    made ZCode block every prompt)."""
    max_rounds = max(1, int(cfg.get("maxRounds", 15)))
    warn_at = int(cfg.get("warnAt", max(1, max_rounds - 3)))
    return max_rounds, max(1, min(warn_at, max_rounds - 1))


def is_reset_bash(tool_name, tool_input):
    if tool_name != "Bash":
        return False
    cmd = str(tool_input.get("command", ""))
    return all(m in cmd for m in RESET_MARKERS)


def is_state_read(tool_name, tool_input):
    if tool_name not in READ_TOOLS:
        return False
    hay = " ".join(str(v) for v in tool_input.values() if isinstance(v, str))
    return "discipline-state" in hay


def junk_prompt(prompt):
    """Bare greetings / keyboard mash would become garbage objectives."""
    if len(prompt) < 40:
        return True
    if re.search(r"(.)\1{6,}", prompt):  # aaaaaaaa…
        return True
    return False


def main():
    cfg = lib.load_config()
    data = lib.read_stdin()
    lib.debug_dump(cfg, f"loop-{mode}", data)

    event = data.get("hook_event_name") or data.get("hookEventName") or ""
    sid = data.get("session_id") or data.get("sessionId") or "default"
    st = lib.load_state()
    sessions = st.setdefault("sessions", {})
    s = sessions.setdefault(str(sid), {"rounds": 0, "objective": "", "updated": 0})

    max_rounds, warn_at = knobs(cfg)

    if mode == "prompt":
        prompt = str(data.get("prompt") or "").strip()
        if not s["objective"] and prompt and not junk_prompt(prompt):
            s["objective"] = prompt[:2000]
            lib.log(f"[{sid}] objective recorded ({len(prompt)} chars)")
        if s["rounds"] < max_rounds:
            s["rounds"] += 1
        s["updated"] = time.time()
        lib.save_state(st)
        r = s["rounds"]
        lib.log(f"[{sid}] round {r}/{max_rounds} ({event})")
        if r >= max_rounds:
            if not s.get("cappedNotice"):
                s["cappedNotice"] = True
                lib.save_state(st)
                lib.emit_context(event,
                    f"DISCIPLINE: loop cap {max_rounds} reached for this session. "
                    f"All tool calls are now denied except /discipline-reset and "
                    f"reads of ~/.zcode/discipline-state/. Finish and report to "
                    f"the user.")
            # already capped: stay silent — every tool deny repeats the reason
        elif r == warn_at:
            lib.emit_context(event,
                f"DISCIPLINE WARNING: round {r} of {max_rounds} for this session. "
                f"Objective: {s['objective'][:500] or '(not captured yet)'} — "
                f"finish or converge NOW; at {max_rounds} tool calls are denied.")
        elif r > warn_at:
            lib.emit_context(event,
                f"DISCIPLINE: round {r}/{max_rounds}. Objective: "
                f"{s['objective'][:500] or '(not captured yet)'} — no adjacent "
                f"work, converge or report.")
        return

    # pretool mode
    tool_name = data.get("tool_name") or data.get("toolName") or ""
    tool_input = data.get("tool_input") or data.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    if is_reset_bash(tool_name, tool_input) or is_state_read(tool_name, tool_input):
        lib.log(f"[{sid}] ALLOW escape-hatch {tool_name} call "
                f"(rounds {s['rounds']}/{max_rounds})")
        return
    if s["rounds"] >= max_rounds:
        lib.log(f"[{sid}] DENY tool call, cap {max_rounds} reached")
        lib.deny_tool(
            f"discipline: loop cap {max_rounds} reached for this session — "
            f"finish and report to the user; /discipline-reset lifts the cap.")


try:
    main()
except BaseException as e:  # nonzero exit blocks prompts — soft-fail, always
    try:
        lib.log(f"loop_cap soft-fail: {e!r}")
    except Exception:
        pass
