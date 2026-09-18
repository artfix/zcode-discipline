#!/usr/bin/env python3
"""Hook B - verification.

posttool mode (PostToolUse on Edit|Write): read the file back; record an
  "unverified edit" marker on success/failure. Never blocks (exit 0) - the
  Stop gate owns the teeth.
stop mode (Stop): if unverified edits exist, veto the stop (exit 2) and tell
  the model to prove its work. ZCode natively caps continuations at 3, so a
  model that cannot prove anything still gets to stop. Gate strength via
  config.stopGate: off | soft (only when verifyCommand is configured) | hard.
"""
import subprocess
import sys
import time
from pathlib import Path

import lib

mode = sys.argv[1] if len(sys.argv) > 1 else "posttool"
MAX_STOP_BLOCKS = 3


def run_verify_command(cfg, cwd):
    cmd = (cfg.get("verifyCommand") or "").strip()
    if not cmd:
        return None
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd or None,
                           capture_output=True, text=True, timeout=55)
        return (p.returncode, (p.stdout or "")[-2000:], (p.stderr or "")[-2000:])
    except Exception as e:
        return (None, "", repr(e))


def main():
    cfg = lib.load_config()
    data = lib.read_stdin()
    lib.debug_dump(cfg, f"verify-{mode}", data)

    sid = str(lib.first_of(data, "session_id", "sessionId", "sessionID", default="default"))
    st = lib.load_state()
    unverified = st.setdefault("unverified", {})
    stop_blocks = st.setdefault("stopBlocks", {})

    if mode == "posttool":
        tool_input = lib.first_of(data, "tool_input", "input", "args", default={}) or {}
        file_path = lib.first_of(tool_input, "file_path", "filePath", "path", "file", default="")
        ok = False
        if file_path:
            try:
                p = Path(str(file_path))
                ok = p.is_file() and p.stat().st_size > 0
            except Exception:
                ok = False
        if ok:
            unverified[sid] = {"file": str(file_path), "ts": time.time(), "failed": False}
            lib.log(f"[{sid}] edit landed: {file_path}")
        else:
            unverified[sid] = {"file": str(file_path), "ts": time.time(), "failed": True}
            lib.log(f"[{sid}] EDIT READ-BACK FAILED: {file_path}")
            lib.CURRENT_EVENT[0] = "PostToolUse"
            lib.emit_context(
                f"DISCIPLINE: VERIFICATION FAILED - edit to {file_path} did not land "
                f"(file missing/empty after write). Re-check and redo the edit.")
        lib.save_state(st)
        return

    # stop mode
    gate = str(cfg.get("stopGate", "soft")).lower()
    if gate == "off":
        return
    entry = unverified.get(sid)
    if not entry:
        stop_blocks.pop(sid, None)
        lib.save_state(st)
        return
    if entry.get("failed"):
        # the last edit never landed; let it stop, the failure was already surfaced
        return

    cwd = lib.first_of(data, "cwd", "project_dir", "workspace", default="") or ""
    has_cmd = bool((cfg.get("verifyCommand") or "").strip())
    if gate == "soft" and not has_cmd:
        return

    if has_cmd:
        lib.CURRENT_EVENT[0] = "Stop"
        rc, out, err = run_verify_command(cfg, cwd)
        if rc == 0:
            unverified.pop(sid, None)
            stop_blocks.pop(sid, None)
            lib.save_state(st)
            lib.log(f"[{sid}] verifyCommand PASSED, stop allowed")
            return
        lib.log(f"[{sid}] verifyCommand FAILED rc={rc}, vetoing stop")
        blocks = stop_blocks.get(sid, 0) + 1
        stop_blocks[sid] = blocks
        lib.save_state(st)
        print(f"discipline: verification FAILED (rc={rc}) - fix before stopping.\n"
              f"stdout tail: {out[-500:]}\nstderr tail: {err[-500:]}", file=sys.stderr)
        if blocks <= MAX_STOP_BLOCKS:
            sys.exit(2)
        lib.log(f"[{sid}] stop-block limit reached, letting it stop")
        return

    # hard gate without command OR soft fallback: no proof mechanism at all
    if gate == "hard":
        blocks = stop_blocks.get(sid, 0) + 1
        stop_blocks[sid] = blocks
        lib.save_state(st)
        lib.log(f"[{sid}] HARD veto: unverified edit {entry.get('file')}")
        print("discipline: unverified edits exist - summarize what you changed and how "
              "you know it works before stopping.", file=sys.stderr)
        if blocks <= MAX_STOP_BLOCKS:
            sys.exit(2)


try:
    main()
except SystemExit:
    raise
except Exception as e:
    lib.log(f"verify internal error: {e!r}")
    sys.exit(0)
