"""Read-only production invariants and mandatory auth/YNAB restore containment.

Call under the release controller's shared maintenance/app lock. No operator
boolean or saved approval can replace accepted mounted configuration plus live
verified origin checks. Private snapshots may include existing runtime metadata.
"""
from pathlib import Path

import gateway_release as common
import ynab_release


def accepted_gateway():
    for owner, label in ((common.ROOT, "gateway"), (ynab_release.ROOT, "YNAB")):
        pending = owner / "pending.json"
        common.require(not pending.exists() and not pending.is_symlink(), "Pending " + label + " recovery blocks authorization release")
    # current() is read-only; constructing Gateway normally creates diagnostics.
    gateway = common.Gateway.__new__(common.Gateway)
    gateway.root = common.ROOT
    common.private(gateway.root)
    record = gateway.current()
    directory = Path(record["directory"])
    profile, auth_profile = gateway.profile(record), gateway.auth_profile(record)
    common.require(common.profiles.read(directory) == profile and
                   common.profiles.read(directory, auth=True) == auth_profile,
                   "Accepted route marker differs from mounted model")
    return record, profile, auth_profile


def baseline():
    record, profile, auth_profile = accepted_gateway()
    stable = common.profile_invariants(profile, auth_profile=auth_profile)
    stable["gateway"] = record
    live = ynab_release.runtime()
    if (ynab_release.ROOT / "current.json").exists() or (ynab_release.ROOT / "current.json").is_symlink():
        controller = ynab_release.Release.__new__(ynab_release.Release)
        controller.root = ynab_release.ROOT
        common.private(controller.root)
        accepted = controller.current()
        common.require(accepted is not None and accepted["runtime"] == live, "YNAB differs from accepted state")
        stable["ynab"] = accepted
        stable["ynab_networks"] = ynab_release.topology(require_app=not accepted.get("disabled"))
    else:
        common.require(not live and profile != "enabled", "Unaccepted YNAB runtime blocks authorization release")
        stable["ynab"] = None
    certs = next(item["Source"] for item in record["runtime"]["Mounts"] if item["Destination"] == "/etc/nginx/certs")
    stable["certificates"] = common.certificate_identity(certs)
    return stable


def require_contained():
    _, profile, auth_profile = accepted_gateway()
    common.require(profile == auth_profile == "disabled", "Accept both authorization and YNAB tombstones before database operations")
    authority = common.ROOT / "origin-ca.pem"
    common.regular(authority)
    # This operator-owned trust anchor is mandatory. ssl.create_default_context
    # still verifies the hostname and certificate while dialing loopback with SNI.
    common.auth_health_once("disabled", False, str(authority))
    common.ynab_health_once("disabled", False, str(authority))
    return True
