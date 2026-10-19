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


def verify(phase, allow_missing_proxy=False):
    if allow_missing_proxy and phase != "host":
        raise ValueError("Optional gateway is only valid during host recovery")
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
        if set(ingress["NetworkSettings"]["Networks"]) != set(NETWORKS):
            raise ValueError("Unexpected ingress network")
    print(
        "PASS: network membership, fixed trust and backend port invariants ("
        + phase
        + ")"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["legacy", "vacant", "host"])
    args = parser.parse_args()
    try:
        verify(args.phase)
    except (
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        raise SystemExit(
            "Preflight failed; inspect drift privately before any mutation."
        ) from None
