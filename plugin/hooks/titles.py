#!/usr/bin/env python3
"""Print {session_uuid: {title, source}} for every session in discipline state.

Reads ZCode's client DB read-only (mode=ro) — returns the same titles the
UI shows, so discipline-status can name sessions like the user sees them.
"""
import json
import sqlite3
from pathlib import Path

STATE = Path.home() / ".zcode/discipline-state/state.json"
DB = Path.home() / ".zcode/cli/db/db.sqlite"


def main():
    try:
        st = json.loads(STATE.read_text())
    except Exception:
        print("{}")
        return
    ids = list(st.get("sessions", {})) + list(st.get("unverified", {}))
    out = {}
    if ids and DB.exists():
        try:
            con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            q = ",".join("?" * len(ids))
            for sid, title, src in con.execute(
                f"SELECT id, title, title_source FROM session WHERE id IN ({q})",
                ids,
            ):
                out[sid] = {"title": title, "source": src}
            con.close()
        except Exception as e:
            print(f"(title lookup failed: {e})", file=__import__("sys").stderr)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
