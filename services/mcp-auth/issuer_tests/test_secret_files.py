"""Exercise Linux's real file-mode/symlink boundary with synthetic files only."""
import os
from pathlib import Path
import tempfile
from unittest import skipUnless, TestCase

from auth_service.secrets import protected_text


@skipUnless(hasattr(os, "O_NOFOLLOW"), "Production file security requires POSIX semantics")
class SecretFiles(TestCase):
    def test_protected_regular_file_and_rejected_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "synthetic"
            secret.write_text("synthetic-value")
            secret.chmod(0o400)
            self.assertEqual(protected_text(secret, maximum=64, uid=os.getuid()), "synthetic-value")
            with self.assertRaises(ValueError):
                protected_text(secret, maximum=64, uid=os.getuid() + 1)
            secret.chmod(0o600)
            with self.assertRaises(ValueError):
                protected_text(secret, maximum=64, uid=os.getuid())
            secret.chmod(0o400)
            alias = root / "alias"
            alias.symlink_to(secret)
            for path, maximum in ((alias, 64), (root, 64), (secret, 2), (root / "missing", 64)):
                with self.assertRaises(ValueError):
                    protected_text(path, maximum=maximum, uid=os.getuid())
