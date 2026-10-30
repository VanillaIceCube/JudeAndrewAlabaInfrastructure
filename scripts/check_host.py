"""Read-only preflight; fails on topology drift. Does not provision or repair."""

import argparse
import json
import subprocess

NETWORKS = {
    "notoli_backend_private": (True, "172.30.88.0/29", {"notoli-backend"}),
    "notoli_default": (False, "172.18.0.0/16", {"notoli-frontend"}),
    "macromapper-ingress": (
        False,
        "172.20.0.0/16",
        {"macromapper-backend", "macromapper-frontend"},
    ),
}


def inspect(kind, name):
    result = subprocess.run(
        ["docker", kind, "inspect", name],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)[0]


def exact_ipam(config, subnet, gateway):
    if not isinstance(config, list) or len(config) != 1 or not isinstance(config[0], dict):
        return False
    entry = dict(config[0])
    # Docker Engine may serialize an omitted optional range as an empty string.
    # No other optional property, range, null or auxiliary address is accepted.
    if entry.get("IPRange") == "":
        entry.pop("IPRange")
    return entry == {"Subnet": subnet, "Gateway": gateway}


def optional_route(auth, allow_missing_proxy=False, *, allow_stopped_gateway=False):
    network, octet, app_name, project, service, label = (
        "mcp_auth_private", "92", "mcp-auth-server", "mcp-auth", "authorization", "MCP authorization"
    ) if auth else ("ynab_mcp_private", "89", "ynab-mcp-gateway-1", "ynab-mcp", "gateway", "YNAB")
    route = inspect("network", network)
    members = {item["Name"]: item for item in route["Containers"].values()}
    allowed = {"host-ingress-proxy": "172.30." + octet + ".2", app_name: "172.30." + octet + ".3"}
    if (not route["Internal"] or route["Driver"] != "bridge" or route.get("EnableIPv6") or
            not exact_ipam(route["IPAM"]["Config"], "172.30." + octet + ".0/29", "172.30." + octet + ".1") or
            not set(members) <= set(allowed) or
            any(item["IPv4Address"].split("/")[0] != allowed[name] for name, item in members.items()) or
            (not allow_missing_proxy and "host-ingress-proxy" not in members)):
        raise ValueError(label + " route topology drift")
    if auth and app_name in members:
        app = inspect("container", app_name)
        labels = app["Config"].get("Labels") or {}
        attachment = app["NetworkSettings"]["Networks"].get(network)
        if (labels.get("com.docker.compose.project") != project or
                labels.get("com.docker.compose.service") != service or attachment is None or
                attachment.get("NetworkID") != route["Id"] or attachment.get("IPAddress") != allowed[app_name] or
                "mcp-auth" not in (attachment.get("Aliases") or [])):
            raise ValueError("Unowned attached authorization endpoint")
    if app_name not in members:
        if not allow_stopped_gateway:
            raise ValueError("Missing required " + label + " gateway endpoint")
        # App-only stop/recovery must not block an unrelated gateway update.
        # Permit only the exact stopped, project-owned container still configured
        # for this network; never a missing/running/disconnected foreign member.
        app = inspect("container", app_name)
        labels = app["Config"].get("Labels") or {}
        attachment = app["NetworkSettings"]["Networks"].get(network)
        state = app["State"]
        if (state.get("Status") != "exited" or state["Running"] or state.get("Dead") or state.get("Restarting")
                or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.service") != service or attachment is None
                or attachment.get("NetworkID") != route["Id"] or attachment.get("IPAddress")):
            raise ValueError("Unowned or inconsistent stopped " + label + " gateway")
    return route


def ynab_route(allow_missing_proxy=False, *, allow_stopped_gateway=False):
    return optional_route(False, allow_missing_proxy, allow_stopped_gateway=allow_stopped_gateway)


def auth_route(allow_missing_proxy=False, *, allow_stopped_gateway=False):
    return optional_route(True, allow_missing_proxy, allow_stopped_gateway=allow_stopped_gateway)


def verify(phase, allow_missing_proxy=False, *, ynab_enabled=False, auth_enabled=False, allow_stopped_gateway=False):
    if allow_missing_proxy and phase != "host":
        raise ValueError("Optional gateway is only valid during host recovery")
    if (ynab_enabled or auth_enabled) and phase != "host":
        raise ValueError("YNAB route requires an existing host gateway")
    proxy = {"legacy": "notoli-proxy", "host": "host-ingress-proxy", "vacant": None}[
        phase
    ]
    for name, (internal, subnet, apps) in NETWORKS.items():
        network = inspect("network", name)
        expected = apps | ({proxy} if proxy else set())
        if network["Internal"] != internal:
            raise ValueError("Network internal flag changed")
        if [p["Subnet"] for p in network["IPAM"]["Config"]] != [subnet]:
            raise ValueError("IPAM changed")
        members = {v["Name"]: v for v in network["Containers"].values()}
        if set(members) != expected and not (allow_missing_proxy and set(members) == apps):
            raise ValueError("Unexpected/missing route-network member")
        if name == "notoli_backend_private":
            if members["notoli-backend"]["IPv4Address"].split("/")[0] != "172.30.88.3":
                raise ValueError("Topology invariant failed")
            if proxy and proxy in members:
                if members[proxy]["IPv4Address"].split("/")[0] != "172.30.88.2":
                    raise ValueError("Topology invariant failed")
        if name == "macromapper-ingress" and phase == "host" and proxy in members:
            if members[proxy]["IPv4Address"].split("/")[0] != "172.20.0.3":
                raise ValueError("MacroMapper proxy trust address changed")
    backend = inspect("container", "notoli-backend")
    if "DJANGO_TRUSTED_PROXY_IPS=172.30.88.2" not in backend["Config"]["Env"]:
        raise ValueError("Proxy trust changed")
    if backend["HostConfig"]["PortBindings"]:
        raise ValueError("Notoli backend exposed")
    if inspect("container", "macromapper-backend")["HostConfig"]["PortBindings"]:
        raise ValueError("MacroMapper backend exposed")
    if proxy and not allow_missing_proxy:
        ingress = inspect("container", proxy)
        if not ingress["State"]["Running"]:
            raise ValueError("Ingress is not running")
        expected_networks = set(NETWORKS) | ({"ynab_mcp_private"} if ynab_enabled else set()) | ({"mcp_auth_private"} if auth_enabled else set())
        if set(ingress["NetworkSettings"]["Networks"]) != expected_networks:
            raise ValueError("Unexpected ingress network")
        if ynab_enabled and ingress["NetworkSettings"]["Networks"]["ynab_mcp_private"]["IPAddress"] != "172.30.89.2":
            raise ValueError("YNAB proxy address drift")
        if auth_enabled and ingress["NetworkSettings"]["Networks"]["mcp_auth_private"]["IPAddress"] != "172.30.92.2":
            raise ValueError("Authorization proxy address drift")
    if ynab_enabled:
        ynab_route(allow_missing_proxy, allow_stopped_gateway=allow_stopped_gateway)
    if auth_enabled:
        auth_route(allow_missing_proxy, allow_stopped_gateway=allow_stopped_gateway)
    print(
        "PASS: network membership, fixed trust and backend port invariants ("
        + phase
        + ")"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["legacy", "vacant", "host"])
    parser.add_argument("--ynab-enabled", action="store_true")
    parser.add_argument("--auth-enabled", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.phase, ynab_enabled=args.ynab_enabled, auth_enabled=args.auth_enabled)
    except (
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        raise SystemExit(
            "Preflight failed; inspect drift privately before any mutation."
        ) from None
