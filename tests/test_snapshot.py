from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "snapshot", Path(__file__).resolve().parents[1] / "scripts/snapshot_sqlite.py"
)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotTests(unittest.TestCase):
    def test_captures_committed_wal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.sqlite3"
            with closing(sqlite3.connect(source)) as live:
                live.execute("PRAGMA journal_mode=WAL")
                live.execute("CREATE TABLE data(value TEXT)")
                live.execute("INSERT INTO data VALUES ('committed')")
                live.commit()
                live.execute("INSERT INTO data VALUES ('uncommitted')")
                record = snapshot.capture(source, root / "recovery")
                self.assertTrue(record["isolated_restore_verified"])
                with closing(
                    sqlite3.connect(root / "recovery/db.sqlite3")
                ) as recovered:
                    self.assertEqual(
                        recovered.execute("SELECT * FROM data").fetchall(),
                        [("committed",)],
                    )
                self.assertEqual(
                    live.execute("SELECT count(*) FROM data").fetchone()[0], 2
                )
                with self.assertRaises(FileExistsError):
                    snapshot.capture(source, root / "recovery")
            self.assertFalse((root / "recovery/restore-check.sqlite3").exists())

    def test_bad_source_never_records_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "broken.sqlite3"
            source.write_text("not a sqlite database")
            with self.assertRaises(sqlite3.DatabaseError):
                snapshot.capture(source, root / "recovery")
            self.assertFalse((root / "recovery/verified.json").exists())
