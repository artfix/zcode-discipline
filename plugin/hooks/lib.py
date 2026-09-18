"""Shared helpers for zcode-discipline hooks.

The hook contract below is VERIFIED against ZCode's own core code
(glm/zcode.cjs: payload builder mNt, output schema AJt, per-event union eYn):

STDIN  (snake_case, Claude-compat): session_id, hook_event_name,
       permission_mode, agent_type, cwd, timestamp, transcript_path,
       prompt (UserPromptSubmit), tool_name/tool_input/tool_use_id (tool
       events), tool_response (PostToolUse), stopHookActive (Stop).

OUTPUT (strict schema, ONLY these top-level keys):
       continue: bool, decision: "approve"|"block", reason, stopReason,
       suppressOutput, systemMessage, additionalContext/additional_context,
       hookSpecificOutput: {hookEventName: <same event>, additionalContext?}
         + PreToolUse only: permissionDecision "allow"|"ask"|"deny",
           permissionDecisionReason, updatedInput.

Design rules:
- Fail-open: internal errors log and exit 0. Deliberate gates emit the
  verified JSON deny/veto and exit 0 (JSON is the first-class mechanism).
- Output carries ONLY schema keys — one extra key = whole output discarded.
"""

import json
import os
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("DISCIPLINE_STATE_DIR", str(Path.home() / ".zcode" / "discipline-state")))
STATE_FILE = STATE_DIR / "state.json"
CONFIG_FILE = STATE_DIR / "config.json"
LOG_FILE = STATE_DIR / "discipline.log"
DEBUG_DIR = STATE_DIR / "debug"
BACKUP_DIR = STATE_DIR / "backups"

DEFAULTS = {
    "debug": True,              # dump raw hook stdin to debug/ (first session confirms live shape)
    "maxRounds": 15,            # tool-deny cap per session
    "warnAt": 12,               # loud re-grounding starts here
    "stopGate": "soft",         # off | soft (block only if verifyCommand set) | hard (block on any unverified edit)
    "verifyCommand": "",        # e.g. "npm test"; run from the session's cwd
    "backups": {"keep": 5, "maxSourceMB": 500},
}


def ensure_dirs():
    for d in (STATE_DIR, DEBUG_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def log(msg):
    try:
        ensure_dirs()
        line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n"
        with open(LOG_FILE, "a") as f:
            f.write(line)
        if LOG_FILE.stat().st_size > 1_000_000:  # 1MB self-rotation
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.old"))
    except Exception:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    try:
        user = json.loads(CONFIG_FILE.read_text())
        if isinstance(user, dict):
            backups = dict(DEFAULTS["backups"])
            backups.update(user.get("backups") or {})
            cfg.update(user)
            cfg["backups"] = backups
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"config parse error ({e}); using defaults")
    return cfg


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"sessions": {}, "unverified": {}, "stopBlocks": {}}


def save_state(st):
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE_FILE)


def read_stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        log(f"stdin not JSON ({e})")
        return {}


def debug_dump(cfg, event, data):
    if not cfg.get("debug"):
        return
    try:
        ensure_dirs()
        if len(list(DEBUG_DIR.glob("*.json"))) < 60:
            (DEBUG_DIR / f"{event}-{int(time.time()*1000)}.json").write_text(
                json.dumps(data, indent=1)[:20000])
    except Exception:
        pass


def emit_context(event_name, text):
    """Inject text into the conversation (verified per-event union member)."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }))


def deny_tool(reason):
    """PreToolUse deny via the verified JSON path (exit 0)."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def veto_stop(reason):
    """Stop veto via the verified top-level keys."""
    print(json.dumps({
        "continue": False,
        "stopReason": reason,
        "reason": reason,
        "systemMessage": reason,
    }))
