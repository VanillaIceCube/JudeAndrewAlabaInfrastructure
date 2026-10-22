from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

spec = importlib.util.spec_from_file_location(
    "snapshot", Path(__file__).resolve().parents[1] / "scripts/snapshot_sqlite.py"
)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotTests(unittest.TestCase):
    def test_live_container_snapshot_includes_wal_outside_single_file_bind(self):
        name = "snapshot-wal-" + uuid.uuid4().hex[:10]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE data(value TEXT)")
                db.commit()
            script = (
                "import sqlite3,time; db=sqlite3.connect('/backend/db.sqlite3'); "
                "db.execute('PRAGMA journal_mode=WAL'); "
                "db.execute(\"INSERT INTO data VALUES ('container-wal')\"); "
                "db.commit(); print('ready',flush=True); time.sleep(600)"
            )

            def docker(*args):
                return subprocess.run(
                    ["docker", *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).stdout

            try:
                docker(
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--network",
                    "none",
                    "--mount",
                    "type=bind,source=" + str(source) + ",target=/backend/db.sqlite3",
                    "python:3.12-alpine",
                    "python",
                    "-c",
                    script,
                )
                deadline = time.monotonic() + 15
                while "ready" not in docker("logs", name):
                    if time.monotonic() >= deadline:
                        self.fail("Container WAL fixture did not initialize")
                    time.sleep(0.1)
                self.assertFalse(Path(str(source) + "-wal").exists())
                snapshot.capture_container(name, root / "recovery")
                with closing(sqlite3.connect(root / "recovery/db.sqlite3")) as db:
                    self.assertEqual(
                        db.execute("SELECT * FROM data").fetchall(),
                        [("container-wal",)],
                    )
                self.assertEqual(
                    docker("inspect", "--format", "{{.State.Running}}", name).strip(),
                    "true",
                )
            finally:
                docker("rm", "-f", name)

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

    def test_capture_container_cleanup_failure_does_not_mask_primary_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "recovery"

            def mock_run(cmd, *args, **kwargs):
                if kwargs.get("check"):
                    raise subprocess.CalledProcessError(1, cmd, output="", stderr="primary container error")
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="cleanup error")

            with patch("subprocess.run", side_effect=mock_run):
                with self.assertRaises(subprocess.CalledProcessError) as cm:
                    snapshot.capture_container("fake-container", destination)
                self.assertEqual(cm.exception.stderr, "primary container error")
