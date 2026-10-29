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


def ynab_route(allow_missing_proxy=False):
    route = inspect("network", "ynab_mcp_private")
    members = {item["Name"]: item for item in route["Containers"].values()}
    allowed = {"host-ingress-proxy": "172.30.89.2", "ynab-mcp-gateway-1": "172.30.89.3"}
    if (not route["Internal"] or route["Driver"] != "bridge" or route.get("EnableIPv6") or
            route["IPAM"]["Config"] != [{"Subnet": "172.30.89.0/29", "Gateway": "172.30.89.1"}] or
            not set(members) <= set(allowed) or
            any(item["IPv4Address"].split("/")[0] != allowed[name] for name, item in members.items()) or
            (not allow_missing_proxy and "host-ingress-proxy" not in members)):
        raise ValueError("YNAB route topology drift")
    return route


def verify(phase, allow_missing_proxy=False, *, ynab_enabled=False):
    if allow_missing_proxy and phase != "host":
        raise ValueError("Optional gateway is only valid during host recovery")
    if ynab_enabled and phase != "host":
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
        expected_networks = set(NETWORKS) | ({"ynab_mcp_private"} if ynab_enabled else set())
        if set(ingress["NetworkSettings"]["Networks"]) != expected_networks:
            raise ValueError("Unexpected ingress network")
        if ynab_enabled and ingress["NetworkSettings"]["Networks"]["ynab_mcp_private"]["IPAddress"] != "172.30.89.2":
            raise ValueError("YNAB proxy address drift")
    if ynab_enabled:
        ynab_route(allow_missing_proxy)
    print(
        "PASS: network membership, fixed trust and backend port invariants ("
        + phase
        + ")"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["legacy", "vacant", "host"])
    parser.add_argument("--ynab-enabled", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.phase, ynab_enabled=args.ynab_enabled)
    except (
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        raise SystemExit(
            "Preflight failed; inspect drift privately before any mutation."
        ) from None
