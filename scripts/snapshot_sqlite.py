"""Capture and restore-check SQLite into a NEW private recovery directory.

Run only within the separately authorized hold. Never modifies the source DB.
This is local recovery evidence; off-host protection remains an operator step.
"""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def capture(source, destination):
    if source.is_symlink() or not source.is_file() or source.stat().st_nlink != 1:
        raise ValueError("Source must be an existing regular database")
    source = source.resolve()
    info = source.stat()
    destination.mkdir(mode=0o700)  # refuse reuse and existing symlinks
    snapshot = destination / "db.sqlite3"
    restored = destination / "restore-check.sqlite3"
    deadline = time.monotonic() + 60

    def progress(status, remaining, total):
        if time.monotonic() >= deadline:
            raise TimeoutError("Snapshot/restore exceeded 60 seconds")

    for origin, target in ((source, snapshot), (snapshot, restored)):
        target.touch(mode=0o600, exist_ok=False)
        with closing(sqlite3.connect(origin.as_uri() + "?mode=ro", uri=True)) as db:
            with closing(sqlite3.connect(target)) as backup:
                db.backup(backup, pages=256, progress=progress, sleep=0.1)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Snapshot/restore integrity failed")
    metadata = {
        "source": str(source),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": oct(info.st_mode & 0o777),
        "bytes": snapshot.stat().st_size,
        "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "isolated_restore_verified": True,
    }
    record = destination / "verified.json"
    record.touch(mode=0o600, exist_ok=False)
    record.write_text(json.dumps(metadata, indent=2) + "\n")
    restored.unlink()
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    capture(args.source, args.destination)
    print("Verified local snapshot and isolated restore; source database unchanged.")
