"""Pure optional-route packaging policy; no credentials, provider or Docker calls."""
import hashlib
import json
from pathlib import Path
import re

PROFILES = {"base", "disabled", "enabled"}
MARKER = "gateway-profile.json"
VHOST = "nginx/vhosts/zz-ynab.conf"
AUTH_MARKER = "mcp-auth-profile.json"
AUTH_VHOST = "nginx/vhosts/zz-mcp-auth.conf"


def selected(environment, *, auth=False):
    profile = environment.get("MCP_AUTH_ROUTE_PROFILE" if auth else "YNAB_ROUTE_PROFILE") or "base"
    if profile not in PROFILES:
        raise ValueError("Invalid permanent YNAB route profile")
    return profile


def descriptor(profile, vhost=None):
    if profile not in PROFILES or (profile == "base") != (vhost is None):
        raise ValueError("Invalid route profile payload")
    return {"version": 1, "profile": profile,
            "vhost_sha256": hashlib.sha256(vhost).hexdigest() if vhost is not None else None}


def read(directory, *, auth=False):
    marker, vhost = directory / (AUTH_MARKER if auth else MARKER), directory / (AUTH_VHOST if auth else VHOST)
    if not marker.exists():
        if vhost.exists():
            raise ValueError("Optional vhost requires an explicit route profile")
        return "base"  # Backwards-compatible accepted base bundles.
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("Invalid route marker")
    record = json.loads(marker.read_text())
    if (not isinstance(record, dict) or set(record) != {"version", "profile", "vhost_sha256"} or
            type(record["version"]) is not int or record["version"] != 1 or
            not isinstance(record["profile"], str) or record["profile"] not in PROFILES):
        raise ValueError("Invalid route marker schema")
    if record["profile"] == "base":
        if vhost.exists() or record["vhost_sha256"] is not None:
            raise ValueError("Base profile contains an optional route")
    elif (vhost.is_symlink() or not vhost.is_file() or
          not isinstance(record["vhost_sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", record["vhost_sha256"]) or
          hashlib.sha256(vhost.read_bytes()).hexdigest() != record["vhost_sha256"]):
        raise ValueError("Optional vhost checksum mismatch")
    return record["profile"]


def apply(model, profile, *, auth=False):
    if profile not in PROFILES:
        raise ValueError("Invalid route profile")
    if profile == "enabled":
        key, name, address = ("mcp_auth_route", "mcp_auth_private", "172.30.92.2") if auth else (
            "ynab_route", "ynab_mcp_private", "172.30.89.2")
        model["networks"][key] = {"name": name, "external": True}
        model["services"]["proxy"]["networks"][key] = {"ipv4_address": address}
    return model


def model_profile(model, *, auth=False):
    if ("mcp_auth_route" if auth else "ynab_route") in model.get("networks", {}):
        return "enabled"
    for volume in model["services"]["proxy"].get("volumes", []):
        if volume["target"] == "/etc/nginx/conf.d" and (Path(volume["source"]) / Path(AUTH_VHOST if auth else VHOST).name).exists():
            return "disabled"
    return "base"


def transition(previous, candidate):
    if previous not in PROFILES or candidate not in PROFILES:
        raise ValueError("Invalid route transition")
    if previous == "base" and candidate == "enabled":
        raise ValueError("Accept a disabled tombstone baseline before route activation")
    if previous != "base" and candidate == "base":
        raise ValueError("Retain the YNAB tombstone; implicit base removal is prohibited")


def transition_pair(previous, candidate, previous_auth, candidate_auth):
    transition(previous, candidate)
    transition(previous_auth, candidate_auth)
    first_tombstone = (previous == "base" and candidate == "disabled" or
                       previous_auth == "base" and candidate_auth == "disabled")
    first_exposure = (candidate == "enabled" and previous != "enabled" or
                      candidate_auth == "enabled" and previous_auth != "enabled")
    if first_tombstone and first_exposure:
        raise ValueError("Accept initial tombstones separately from first route exposure")
