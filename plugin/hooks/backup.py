#!/usr/bin/env python3
"""Hook C - durability. Fires on SessionStart(matcher=startup) only.

Takes a consistent snapshot of ~/.zcode/cli/db/db.sqlite via the sqlite3
backup API (WAL-safe), gzips it into discipline-state/backups/, rotates
keep-N. Skips silently if the source is bigger than maxSourceMB. Never
blocks the session: all errors are logged and exit 0.
"""
import gzip
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import lib

DB = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


def main():
    cfg = lib.load_config()
    data = lib.read_stdin()
    lib.debug_dump(cfg, "session-start", data)
    lib.ensure_dirs()

    if not DB.is_file():
        lib.log(f"backup skipped: {DB} not found")
        return
    max_mb = int(cfg.get("backups", {}).get("maxSourceMB", 500))
    size_mb = DB.stat().st_size / 1_000_000
    if size_mb > max_mb:
        lib.log(f"backup skipped: db {size_mb:.0f}MB > cap {max_mb}MB")
        return

    keep = int(cfg.get("backups", {}).get("keep", 5))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = lib.BACKUP_DIR / f"db-{stamp}.sqlite.gz"
    t0 = time.time()

    src = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        dst = sqlite3.connect(str(tmp_path))
        src.backup(dst)  # consistent snapshot incl. WAL content, C speed
        dst.close()
        src.close()
        with open(tmp_path, "rb") as fin, gzip.open(dest, "wb", compresslevel=6) as gz:
            shutil.copyfileobj(fin, gz)
    finally:
        tmp_path.unlink(missing_ok=True)

    lib.log(f"backup ok: {dest.name} ({dest.stat().st_size/1_000_000:.1f}MB gz, "
            f"source {size_mb:.0f}MB, {time.time()-t0:.1f}s)")

    backups = sorted(lib.BACKUP_DIR.glob("db-*.sqlite.gz"))
    if len(backups) > keep:
        for old in backups[:-keep]:
            old.unlink()
            lib.log(f"backup rotated out: {old.name}")


try:
    main()
except SystemExit:
    raise
except Exception as e:
    lib.log(f"backup internal error: {e!r}")
    sys.exit(0)
