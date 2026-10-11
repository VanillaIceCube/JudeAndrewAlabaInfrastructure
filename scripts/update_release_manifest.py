"""Refresh the vendored-release manifest, or verify it in infrastructure CI."""

import argparse
import importlib.util
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app-release/v1"
spec = importlib.util.spec_from_file_location("parity", SOURCE / "check_parity.py")
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = {
        "contract_version": 1,
        "files": {
            target: parity.digest((SOURCE / source).read_bytes())
            for target, source in parity.FILES.items()
        },
        "workflow_sha256": parity.digest((SOURCE / "workflow.yml").read_bytes()),
    }
    path = SOURCE / "manifest.json"
    if args.check:
        if json.loads(path.read_text(encoding="utf-8")) != manifest:
            raise SystemExit(
                "Shared release manifest is stale; regenerate after reviewing common changes"
            )
        print("Shared release manifest matches all common files")
    else:
        path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
