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


def verify(allow_missing_proxy=False, allow_missing_apps=False):
    proxy = "host-ingress-proxy"
    attached = set()
    for name, (internal, subnet, apps) in NETWORKS.items():
        network = inspect("network", name)
        expected = apps | {proxy}
        if network["Internal"] != internal:
            raise ValueError("Network internal flag changed")
        if [p["Subnet"] for p in network["IPAM"]["Config"]] != [subnet]:
            raise ValueError("IPAM changed")
        members = {v["Name"]: v for v in network["Containers"].values()}
        attached.update(members)
        required = (set() if allow_missing_apps else apps) | (
            set() if allow_missing_proxy else {proxy}
        )
        if not required <= members.keys() <= expected:
            raise ValueError("Unexpected/missing route-network member")
        if name == "notoli_backend_private":
            if (
                "notoli-backend" in members
                and members["notoli-backend"]["IPv4Address"].split("/")[0]
                != "172.30.88.3"
            ):
                raise ValueError("Topology invariant failed")
            if proxy in members:
                if members[proxy]["IPv4Address"].split("/")[0] != "172.30.88.2":
                    raise ValueError("Topology invariant failed")
        if name == "macromapper-ingress" and proxy in members:
            if members[proxy]["IPv4Address"].split("/")[0] != "172.20.0.3":
                raise ValueError("MacroMapper proxy trust address changed")
    for name in ("notoli-backend", "macromapper-backend"):
        if name in attached:
            backend = inspect("container", name)
            if backend["HostConfig"]["PortBindings"]:
                raise ValueError("Backend unexpectedly exposes a host port")
            if (
                name == "notoli-backend"
                and "DJANGO_TRUSTED_PROXY_IPS=172.30.88.2"
                not in backend["Config"]["Env"]
            ):
                raise ValueError("Proxy trust changed")
    if not allow_missing_proxy:
        ingress = inspect("container", proxy)
        if not ingress["State"]["Running"]:
            raise ValueError("Ingress is not running")
        if set(ingress["NetworkSettings"]["Networks"]) != set(NETWORKS):
            raise ValueError("Unexpected ingress network")
    return attached


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        verify()
        print("Gateway and application network boundaries verified")
    except (
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        raise SystemExit(
            "Preflight failed; inspect drift privately before any mutation."
        ) from None
