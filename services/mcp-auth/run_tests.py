"""Stable CI entry point: isolated local Docker fixture, never production."""
import uuid
import argparse
import os
from run_container_tests import main, cleanup

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup")
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.cleanup)
    else:
        main(os.environ.get("MCP_AUTH_TEST_ID") or "mcp-auth-test-" + uuid.uuid4().hex)
