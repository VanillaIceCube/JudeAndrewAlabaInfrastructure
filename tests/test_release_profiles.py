"""Exercise the common release suite against explicit app policies, including a new app."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app-release/v1"
spec = importlib.util.spec_from_file_location(
    "release_parity", SOURCE / "check_parity.py"
)
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)


class ReleaseProfileTests(unittest.TestCase):
    def test_shared_suites_cover_existing_and_template_profiles(self):
        for profile in sorted((ROOT / "tests/fixtures/release-profiles").iterdir()):
            with (
                self.subTest(app=profile.name),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                production = root / "deploy/production"
                production.mkdir(parents=True)
                for name in ("release.py", "build_bundle.py"):
                    shutil.copyfile(SOURCE / name, production / name)
                for name in ("app.json", "compose.yml"):
                    shutil.copyfile(profile / name, production / name)
                shutil.copytree(SOURCE / "tests", root / "deploy/tests")
                shutil.copyfile(
                    SOURCE / "check_parity.py", root / "deploy/check_parity.py"
                )
                workflow = root / ".github/workflows/ci-deploy.yml"
                workflow.parent.mkdir(parents=True)
                config = json.loads((production / "app.json").read_text())
                workflow.write_text(
                    parity.render_workflow(
                        (SOURCE / "workflow.yml").read_text(), config
                    ),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "deploy/tests",
                        "-v",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
