"""Read-only source/digest/secret preflight, reusing the existing runtime policy."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ynab_runtime_preflight", HERE.parent / "ynab-mcp/validate.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def validate(image, token, identity, public_key):
    for path in (token, identity, public_key):
        runtime.validate(image, path)
    config = json.loads(identity.read_text())
    if (set(config) != {"issuer", "owner", "clients"} or not isinstance(config["issuer"], str)
            or not config["issuer"].startswith("https://") or not isinstance(config["owner"], str)
            or not config["owner"] or not isinstance(config["clients"], list)
            or not 1 <= len(config["clients"]) <= 8
            or any(not isinstance(client, str) or not client for client in config["clients"])):
        raise ValueError("Invalid gateway identity configuration")
    if not public_key.read_text().startswith("-----BEGIN PUBLIC KEY-----"):
        raise ValueError("Expected issuer RSA public key; no private key is accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--public-key-file", type=Path, required=True)
    args = parser.parse_args()
    validate(args.image, args.token_file, args.identity_file, args.public_key_file)
    print("Private gateway metadata preflight passed; cryptographic startup validation still required; no service started")
