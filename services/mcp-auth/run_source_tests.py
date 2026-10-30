"""Run real library flows with disposable synthetic credentials and SQLite state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="mcp-auth-tests-") as directory:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_path = Path(directory) / "synthetic.pem"
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        env = dict(os.environ, DJANGO_SETTINGS_MODULE="issuer_tests.settings",
                   MCP_AUTH_TEST_KEY_PATH=str(key_path), MCP_AUTH_TEST_DB_PATH=str(Path(directory) / "test.sqlite3"),
                   PYTHONPATH=os.pathsep.join([str(root), str(root / "backend"), os.environ.get("PYTHONPATH", "")]))
        subprocess.run([sys.executable, str(root / "backend/manage.py"), "makemigrations", "--check", "--dry-run"],
                       env=env, cwd=root, check=True)
        result = subprocess.run([sys.executable, str(root / "backend/manage.py"), "test", "issuer_tests", "--verbosity", "2", *sys.argv[1:]],
                                env=env, cwd=root)
        peak = Path("/sys/fs/cgroup/memory.peak")
        if peak.exists():
            print("Synthetic source-suite cgroup peak bytes:", peak.read_text().strip())
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
