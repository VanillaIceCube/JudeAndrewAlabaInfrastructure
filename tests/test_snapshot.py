from contextlib import closing
import importlib.util
import io
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

    def container_run(self, cleanup, primary=None):
        def run(cmd, **kwargs):
            if cmd[:2] == ["docker", "cp"]:
                with closing(sqlite3.connect(cmd[-1])) as db:
                    db.execute("CREATE TABLE data(value TEXT)")
                    db.commit()
            elif "os.unlink" in cmd[-2]:
                self.assertEqual(cmd[:5], ["docker", "exec", "fake-container", "python", "-c"])
                self.assertRegex(cmd[-1], r"^/tmp/ingress-snapshot-[a-f0-9]{32}\.sqlite3$")
                self.assertNotIn("/backend/db.sqlite3", cmd[-2:])
                if isinstance(cleanup, Exception):
                    raise cleanup
                return subprocess.CompletedProcess(cmd, cleanup, stderr="private-cleanup-output")
            elif primary is not None:
                raise primary
            return subprocess.CompletedProcess(
                cmd, 0, stdout='{"uid":0,"gid":0,"mode":"0o600"}'
            )
        return run

    def test_cleanup_failures_preserve_primary_errors_and_interruptions(self):
        primary_errors = (
            subprocess.CalledProcessError(1, ["docker"], stderr="private-primary-output"),
            KeyboardInterrupt(),
        )
        cleanup_errors = (1, subprocess.TimeoutExpired(["docker"], 30, stderr="private-timeout-output"))
        for primary in primary_errors:
            for cleanup in cleanup_errors:
                with self.subTest(primary=type(primary).__name__, cleanup=type(cleanup).__name__), \
                        tempfile.TemporaryDirectory() as directory:
                    stderr = io.StringIO()
                    with patch.object(snapshot.subprocess, "run", side_effect=self.container_run(cleanup, primary)), \
                            patch("sys.stderr", stderr), self.assertRaises(type(primary)) as raised:
                        snapshot.capture_container("fake-container", Path(directory) / "recovery")
                    self.assertIs(raised.exception, primary)
                    warning = stderr.getvalue()
                    self.assertIn("snapshot cleanup failed after primary error", warning)
                    self.assertIn("fake-container:/tmp/ingress-snapshot-", warning)
                    self.assertNotIn("private-", warning)

    def test_cleanup_failure_after_snapshot_reports_safe_artifact_details(self):
        for cleanup, diagnostic in (
            (7, "Cleanup command exited with code 7"),
            (subprocess.TimeoutExpired(["docker"], 30, stderr="private-timeout-output"), "TimeoutExpired"),
            (OSError("private-exception-message"), "OSError"),
        ):
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as directory:
                with patch.object(snapshot.subprocess, "run", side_effect=self.container_run(cleanup)), \
                        self.assertRaises(RuntimeError) as raised:
                    snapshot.capture_container("fake-container", Path(directory) / "recovery")
                message = str(raised.exception)
                self.assertIn("Snapshot cleanup failed", message)
                self.assertIn(diagnostic, message)
                self.assertIn("fake-container:/tmp/ingress-snapshot-", message)
                self.assertNotIn("private-", message)

    def test_success_cleans_only_the_copied_temporary_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(snapshot.subprocess, "run", side_effect=self.container_run(0)) as run:
                result = snapshot.capture_container("fake-container", Path(directory) / "recovery")
            commands = [call.args[0] for call in run.call_args_list]
            remote = commands[0][-1]
            self.assertEqual(commands[1][2], "fake-container:" + remote)
            self.assertEqual(commands[2][-1], remote)
            self.assertEqual(len(commands), 3)
            self.assertTrue(result["isolated_restore_verified"])
