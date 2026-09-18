"""Shared state/config/log helpers for zcode-discipline hooks.

Design rules:
- Fail-open: any internal error logs and exits 0 (never blocks John's work
  because of a plugin bug). Deliberate blocks (loop cap, stop veto) exit 2.
- Strict output schema: emit nothing unless we mean to inject context.
- Exact stdin field names are version-dependent; everything is read
  defensively through known key candidates. debug:true dumps raw stdin.
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
    "debug": True,              # dump raw hook stdin to debug/ until format confirmed
    "maxRounds": 15,            # tool-deny cap per session
    "warnAt": 12,               # loud re-grounding starts here
    "stopGate": "soft",         # off | soft (block only if verifyCommand set) | hard (block on any unverified edit)
    "verifyCommand": "",        # e.g. "npm test"; run from the session's project dir
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
            LOG_FILE.rename(LOG_FILE.with_suffix(".log.old"))
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
        n = len(list(DEBUG_DIR.glob("*.json")))
        if n < 60:
            (DEBUG_DIR / f"{event}-{int(time.time()*1000)}.json").write_text(
                json.dumps(data, indent=1)[:20000])
    except Exception:
        pass


def first_of(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def emit_context(text):
    """Best-effort additionalContext injection (Claude-compat shape).
    If ZCode's strict schema rejects it, the run logs a validation note and
    nothing is injected - never fatal."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": CURRENT_EVENT[0],
            "additionalContext": text,
        }
    }))


CURRENT_EVENT = ["UserPromptSubmit"]
