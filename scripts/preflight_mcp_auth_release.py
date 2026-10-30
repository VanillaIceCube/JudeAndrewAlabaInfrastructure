"""Fresh exact-image prerequisite for the independently released MCP issuer."""
import os

from check_ynab_image_audit import require
from preflight_ynab_release import audit_local, inspect


def preflight(image, scanner, cache):
    require(os.name == "posix", "Use the disposable Linux release preflight")
    image_id = inspect(image, "authorization")
    audit_local(image_id, "authorization", scanner, cache)
    return {"reference": image, "image_id": image_id}
