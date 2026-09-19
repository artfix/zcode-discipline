#!/usr/bin/env python3
"""Hook B - verification. Contract: see lib.py docstring.

posttool mode (PostToolUse on Edit|Write): read tool_input["file_path"] back;
  record an unverified marker. Failure injects additionalContext.
stop mode (Stop): unverified edits -> {"continue": false} veto with reason;
  ZCode natively caps Stop continuations (stopHookActive flag arrives on the
  retry), we also cap our own blocks at 3.
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
    # stopGate/verifyCommand come from config.json over lib defaults; no
    # ${user_config.*} args — ZCode does not expand those placeholders, and
    # the old --verify-command arg would have split "npm run test" anyway.
    cfg = lib.load_config()
    data = lib.read_stdin()
    lib.debug_dump(cfg, f"verify-{mode}", data)

    event = data.get("hook_event_name") or data.get("hookEventName") or ""
    sid = str(data.get("session_id") or data.get("sessionId") or "default")
    st = lib.load_state()
    unverified = st.setdefault("unverified", {})
    stop_blocks = st.setdefault("stopBlocks", {})

    if mode == "posttool":
        tool_input = data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or ""
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
            lib.emit_context(event,
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
        # the last edit never landed; failure was already surfaced - let it stop
        return

    cwd = data.get("cwd") or ""
    has_cmd = bool((cfg.get("verifyCommand") or "").strip())
    if gate == "soft" and not has_cmd:
        return

    if has_cmd:
        rc, out, err = run_verify_command(cfg, cwd)
        if rc == 0:
            unverified.pop(sid, None)
            stop_blocks.pop(sid, None)
            lib.save_state(st)
            lib.log(f"[{sid}] verifyCommand PASSED, stop allowed")
            return
        blocks = stop_blocks.get(sid, 0) + 1
        stop_blocks[sid] = blocks
        lib.save_state(st)
        lib.log(f"[{sid}] verifyCommand FAILED rc={rc}, stop veto #{blocks}")
        if blocks <= MAX_STOP_BLOCKS:
            lib.veto_stop(
                f"discipline: verification FAILED (rc={rc}) - fix before stopping. "
                f"stdout tail: {out[-300:]} stderr tail: {err[-300:]}")
        else:
            lib.log(f"[{sid}] stop-block limit reached, letting it stop")
        return

    # hard gate without a command: model must explain its proof in words
    if gate == "hard":
        blocks = stop_blocks.get(sid, 0) + 1
        stop_blocks[sid] = blocks
        lib.save_state(st)
        lib.log(f"[{sid}] HARD veto: unverified edit {entry.get('file')} (#{blocks})")
        if blocks <= MAX_STOP_BLOCKS:
            lib.veto_stop(
                "discipline: unverified edits exist - summarize what you changed "
                "and how you know it works before stopping.")


try:
    main()
except BaseException as e:  # nonzero exit blocks prompts/stops — soft-fail
    try:
        lib.log(f"verify soft-fail: {e!r}")
    except Exception:
        pass
