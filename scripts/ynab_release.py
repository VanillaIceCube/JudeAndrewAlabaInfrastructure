"""Owner-operated, stateless YNAB-only Linux release/recovery transaction.

Uses existing durable/private/lock/Docker primitives. No database, ingress,
network lifecycle, automatic deployment trigger or financial request is owned here.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import uuid

import gateway_release as common
from preflight_ynab_release import preflight

ROOT = Path("/opt/ynab-mcp-deploy")
REPO = Path(__file__).resolve().parents[1]
PROJECT = "ynab-mcp"
NAMES = {"gateway": "ynab-mcp-gateway-1", "egress": "ynab-mcp-egress-1"}
SECRET_NAMES = ("ynab_api_token", "gateway_identity.json", "oauth_public_key.pem")
FILES = {"compose.yml": "services/ynab-gateway/compose.yml",
         "network.compose.yml": "services/ynab-gateway/network.compose.yml",
         "squid.conf": "services/ynab-gateway/squid.conf"}
NETWORKS = {
    "ynab_mcp_private": (True, "172.30.89.0/29", {"host-ingress-proxy": "172.30.89.2", NAMES["gateway"]: "172.30.89.3"}),
    "ynab_mcp_egress_private": (True, "172.30.90.0/29", {NAMES["egress"]: "172.30.90.2", NAMES["gateway"]: "172.30.90.3"}),
    "ynab_mcp_egress_public": (False, "172.30.91.0/29", {NAMES["egress"]: "172.30.91.2"}),
}
PROBE = """import json,socket,urllib.request
for path in ('/health/live','/health/ready'):
 with urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=5) as response:
  assert response.status==200
socket.create_connection(('ynab-egress',3128),timeout=5).close()
"""
require = common.require


@contextmanager
def locks(directory=common.LOCK.parent):
    with common.maintenance(directory / "maintenance.lock", shared=True):
        with common.maintenance(directory / "ynab-mcp.lock"):
            yield


def files_identity(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Symlinked release file")
        if path.is_file():
            info = common.regular(path).stat()
            result[str(path.relative_to(directory))] = [
                info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
                hashlib.sha256(path.read_bytes()).hexdigest()]
    return result


def source_files(source):
    require(common.SHA.fullmatch(source), "Full source commit required")
    head = common.run(["git", "-C", REPO, "rev-parse", "HEAD"]).strip()
    require(head == source, "Run the transaction from the reviewed exact source checkout")
    require(not common.run(["git", "-C", REPO, "status", "--porcelain"]).strip(), "Reviewed checkout must be clean")
    return {name: common.run(["git", "-C", REPO, "show", source + ":" + path]) for name, path in FILES.items()}


def companions():
    proxy = common.inspect("container", "host-ingress-proxy")
    accepted = common.read(common.ROOT / "current.json")
    directory = Path(accepted["directory"])
    require(directory.parent == common.ROOT / "releases", "Invalid accepted gateway directory")
    common.private(directory)
    profile = common.profiles.model_profile(common.read(directory / "model.json"))
    require(accepted.get("profile", profile) == profile and common.runtime() == accepted["runtime"],
            "Gateway differs from accepted profile/runtime")
    enabled = profile == "enabled"
    require(("ynab_mcp_private" in proxy["NetworkSettings"]["Networks"]) == enabled,
            "Gateway route attachment differs from accepted profile")
    stable = common.invariants(ynab_enabled=enabled)
    stable["proxy"] = common.runtime()
    certs = next(mount["Source"] for mount in proxy["Mounts"] if mount["Destination"] == "/etc/nginx/certs")
    stable["certificates"] = common.certificate_identity(certs)
    return stable


def topology(*, require_app=False):
    result = {}
    for name, (internal, subnet, allowed) in NETWORKS.items():
        network = common.inspect("network", name)
        ipam = network["IPAM"]["Config"]
        require(network["Driver"] == "bridge" and network["Internal"] == internal and not network.get("EnableIPv6")
                and len(ipam) == 1 and ipam[0]["Subnet"] == subnet and
                ipam[0].get("Gateway") == str(ipaddress.ip_network(subnet).network_address + 1),
                "YNAB network policy drift")
        members = {member["Name"]: member for member in network["Containers"].values()}
        require(set(members) <= set(allowed), "Unexpected YNAB network member")
        require(all(member["IPv4Address"].split("/")[0] == allowed[member_name]
                    for member_name, member in members.items()), "YNAB endpoint address drift")
        if require_app:
            require(set(allowed) - {"host-ingress-proxy"} <= set(members), "Missing app network endpoint")
        result[name] = network["Id"]
    return result


def runtime():
    # Use inspect only for the exact project-labelled names. Unknown project
    # members block instead of being silently adopted or removed as orphans.
    ids = set(common.docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT).split())
    for name in NAMES.values():
        ids.update(common.docker("ps", "-aq", "--filter", "name=^/" + re.escape(name) + "$").split())
    result = {}
    for container_id in ids:
        value = common.inspect("container", container_id)
        name = value["Name"].removeprefix("/")
        require(name in NAMES.values(), "Unmanaged YNAB project member")
        service = next(key for key, expected in NAMES.items() if expected == name)
        require(value["Config"]["Labels"].get("com.docker.compose.service") == service and
                value["Config"]["Labels"].get("com.docker.compose.project") == PROJECT, "Service label drift")
        value["Mounts"] = sorted(value["Mounts"], key=lambda mount: mount["Destination"])
        result[service] = {key: value[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}
        result[service]["running"] = value["State"]["Running"]
        result[service]["started"] = value["State"]["StartedAt"]
        result[service]["networks"] = {name: item["IPAddress"] for name, item in value["NetworkSettings"]["Networks"].items()}
        result[service]["aliases"] = {name: sorted(item.get("Aliases") or [])
                                      for name, item in value["NetworkSettings"]["Networks"].items()}
    return result


class Release:
    def __init__(self, root=ROOT, scanner=None, cache=None):
        self.root, self.scanner, self.cache = root, scanner, cache
        common.private(root)
        for name in ("releases", "records", "attempts"):
            common.private(root / name)
        common.DIAGNOSTICS = root / "diagnostics"
        common.DIAGNOSTICS.mkdir(mode=0o700, exist_ok=True)
        common.private(common.DIAGNOSTICS)

    def directory(self, record):
        path = Path(record["directory"])
        require(path.parent == self.root / "releases" and common.SHA.fullmatch(record["source"]), "Invalid release record")
        common.private(path)
        require(files_identity(path) == record["files"], "Matched release files changed")
        services = common.read(path / "model.json").get("services", {})
        require(set(services) == set(NAMES) and record.get("images") == {
            role: service.get("image") for role, service in services.items()},
            "Artifact references differ from matched Compose model")
        return path

    def current(self):
        if not (self.root / "current.json").exists():
            require(not runtime(), "Unmanaged initial YNAB containers require operator review")
            return None
        record = common.read(self.root / "current.json")
        self.directory(record)
        require(record["runtime"] == runtime(), "Live app drift from accepted state")
        return record

    def save(self, record):
        require(re.fullmatch(r"[a-f0-9]{40}-[a-f0-9]{32}", record["id"]), "Invalid release identity")
        common.atomic(self.root / "records" / (record["id"] + ".json"), record)
        common.atomic(self.root / "current.json", record)

    def compose(self, directory, *arguments):
        return common.docker("compose", "-p", PROJECT, "-f", directory / "model.json", "--profile", "manual-gateway", *arguments)

    def ownership(self, records, *, strict_limits=True):
        """Recover only the exact project's old/candidate images and bind files."""
        choices = []
        for record in records:
            if record:
                directory = self.directory(record)
                choices.append((record, common.read(directory / "model.json")))
        for service, live in runtime().items():
            host = live["HostConfig"]
            require(host.get("ReadonlyRootfs") and not host.get("Privileged") and not host.get("PortBindings")
                    and set(host.get("CapDrop") or []) == {"ALL"} and not host.get("CapAdd") and
                    host.get("SecurityOpt") in (["no-new-privileges"], ["no-new-privileges:true"]),
                    "Unsafe app container drift")
            if service == "gateway":
                ynab = [value for value in live["Config"].get("Env", []) if value.startswith("YNAB_")]
                require(sorted(ynab) == ["YNAB_ALLOW_WRITES=0", "YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1"], "Unsafe financial environment")
            binds = {(mount["Destination"], mount["Source"], not mount["RW"])
                     for mount in live["Mounts"] if mount["Type"] == "bind"}
            require(all(mount["Type"] in {"bind", "tmpfs"} for mount in live["Mounts"]), "Unexpected persistent volume")
            matched = False
            for record, model in choices:
                expected = model["services"][service]
                network_key, alias = ("route", "ynab-mcp-gateway") if service == "gateway" else ("egress_private", "ynab-egress")
                require(alias in expected["networks"][network_key].get("aliases", []), "Missing required app DNS alias")
                image_id = common.inspect("image", record["images"][service])["Id"]
                mounts = {(mount["target"], mount["source"], mount.get("read_only", False)) for mount in expected["volumes"]}
                networks = {model["networks"][key]["name"]: value["ipv4_address"] for key, value in expected["networks"].items()}
                network_match = live["networks"] == networks or (not live["running"] and
                    set(live["networks"]) <= set(networks) and not any(live["networks"].values()))
                aliases_match = not live["running"] or all(set(value.get("aliases", [])) <=
                    set(live["aliases"].get(model["networks"][key]["name"], []))
                    for key, value in expected["networks"].items())
                limits_match = (host.get("Memory") == expected["mem_limit"] and
                    host.get("PidsLimit") == expected["pids_limit"] and
                    host.get("NanoCpus", 0) == round(float(expected.get("cpus", 0)) * 1_000_000_000) and
                    host.get("RestartPolicy", {}).get("Name") == expected["restart"])
                if (live["Image"] == image_id and binds == mounts and live["Config"]["User"] == expected["user"]
                        and network_match and aliases_match and (not strict_limits or limits_match)):
                    matched = True
            require(matched, "Container differs from old/candidate release ownership")

    def ready(self):
        for attempt in range(6):
            try:
                require(set(runtime()) == set(NAMES) and all(value["running"] for value in runtime().values()), "App is stopped")
                common.docker("exec", NAMES["gateway"], "/usr/local/bin/python", "-c", PROBE, timeout=15)
                return
            except common.CommandTimeout:
                raise
            except common.ReleaseError:
                if attempt == 5:
                    raise common.ReleaseError("Non-financial readiness failed") from None
                time.sleep(1)

    def stage(self, source, images, secrets):
        recipe = source_files(source)
        require(set(images) == set(NAMES) and set(secrets) == set(SECRET_NAMES), "Incomplete app inputs")
        spec = importlib.util.spec_from_file_location("ynab_secret_preflight", REPO / "services/ynab-gateway/validate.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        validator.validate(images["gateway"], *(secrets[name] for name in SECRET_NAMES))
        directory = self.root / "releases" / (source + "-" + uuid.uuid4().hex)
        directory.mkdir(mode=0o700)
        for name, content in recipe.items():
            (directory / name).write_text(content)
            (directory / name).chmod(0o600)
        secret_root = directory / "secrets"
        secret_root.mkdir(mode=0o700)
        for name, path in secrets.items():
            target = secret_root / name
            shutil.copyfile(common.regular(path), target)
            os.chown(target, 65532, 65532)
            target.chmod(0o400)
        environment = {key: os.environ[key] for key in ("PATH", "DOCKER_HOST", "DOCKER_CONTEXT") if key in os.environ}
        for role, reference in images.items():
            repository, digest = reference.split("@sha256:")
            environment["YNAB_" + role.upper() + "_REPOSITORY"] = repository
            environment["YNAB_" + role.upper() + "_SHA256"] = digest
        environment.update(YNAB_TOKEN_FILE=str(secret_root / SECRET_NAMES[0]),
            YNAB_GATEWAY_IDENTITY_FILE=str(secret_root / SECRET_NAMES[1]), YNAB_OAUTH_PUBLIC_KEY_FILE=str(secret_root / SECRET_NAMES[2]))
        result = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-p", PROJECT,
            "-f", str(directory / "compose.yml"), "-f", str(directory / "network.compose.yml"),
            "--profile", "manual-gateway", "config", "--format", "json"], env=environment, capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, "Canonical app configuration failed")
        model = json.loads(result.stdout)
        require(set(model["services"]) == set(NAMES) and all(not service.get("ports") for service in model["services"].values()), "Unexpected service/host publication")
        require({name: service["image"] for name, service in model["services"].items()} == images, "Immutable image mismatch")
        require(all(network.get("external") for network in model["networks"].values()), "App cannot create networks")
        for service in model["services"].values():
            # Compose's JSON renderer emits parsed byte limits as decimal text;
            # Docker inspect reports Memory as an integer. Persist that same
            # exact byte value so ownership checks can compare without coercion.
            memory = service.get("mem_limit")
            require(type(memory) is int or (type(memory) is str and re.fullmatch(r"[0-9]+", memory)),
                    "Invalid parsed app memory limit")
            service["mem_limit"] = int(memory)
            require(service["mem_limit"] > 0, "Invalid parsed app memory limit")
        common.atomic(directory / "model.json", model)
        common.durable_tree(directory)
        return {"id": directory.name, "source": source, "directory": str(directory), "images": images,
                "files": files_identity(directory)}

    def deploy(self, source, images, secrets, *, initial=False):
        require(not (self.root / "pending.json").exists(), "Pending release blocks retry; recover explicitly")
        previous = self.current()
        require(previous is not None or initial, "Initial activation requires explicit initial operation")
        before = companions()
        networks = topology(require_app=bool(previous and not previous.get("disabled")))
        # No mutating app command can run unless BOTH exact roles pass new scans.
        preflight(images, self.scanner, self.cache)
        candidate = self.stage(source, images, secrets)
        self.activate(candidate, previous, before, networks)

    def stage_only(self, source, images, secrets):
        require(not (self.root / "pending.json").exists(), "Pending release blocks staging")
        self.current()
        preflight(images, self.scanner, self.cache)
        candidate = dict(self.stage(source, images, secrets), staged=True)
        common.atomic(self.root / "records" / (candidate["id"] + ".json"), candidate)
        return candidate["id"]

    def promote(self, identity, *, initial=False):
        require(not (self.root / "pending.json").exists(), "Pending release blocks promotion")
        require(re.fullmatch(r"[a-f0-9]{40}-[a-f0-9]{32}", identity), "Invalid staged identity")
        candidate = common.read(self.root / "records" / (identity + ".json"))
        require(candidate.get("staged") is True and "runtime" not in candidate, "Expected an unaccepted staged candidate")
        self.directory(candidate)
        previous = self.current()
        require(previous is not None or initial, "Initial activation requires explicit initial operation")
        before = companions()
        networks = topology(require_app=bool(previous and not previous.get("disabled")))
        preflight(candidate["images"], self.scanner, self.cache)
        self.activate(candidate, previous, before, networks)

    def activate(self, candidate, previous, before, networks):
        self.ownership([previous])
        journal = {"id": uuid.uuid4().hex, "phase": "prepared", "candidate": candidate, "previous": previous,
                   "companions": before, "networks": networks}
        common.atomic(self.root / "pending.json", journal)
        try:
            journal["phase"] = "switching"
            common.atomic(self.root / "pending.json", journal)
            self.compose(self.directory(candidate), "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "egress", "gateway")
            self.ready()
            self.ownership([candidate])
            require(companions() == before and topology(require_app=True) == networks, "Companion/network/certificate identity changed")
            candidate.update(runtime=runtime(), disabled=False, previous=previous["id"] if previous else None)
            candidate.pop("staged", None)
            self.save(candidate)
            journal["phase"] = "accepted"
            common.atomic(self.root / "pending.json", journal)
            self.finish(journal)
        except BaseException:
            # Includes interruption: preserve barrier and matched records. Never
            # retry an ambiguous Docker mutation or automatically choose rollback.
            raise common.ReleaseError("Release interrupted/failed; explicit recovery required") from None

    def finish(self, journal):
        require(re.fullmatch(r"[a-f0-9]{32}", journal["id"]), "Invalid attempt identity")
        common.atomic(self.root / "attempts" / (journal["id"] + ".json"), journal)
        common.atomic(self.root / "last-attempt.json", {"id": journal["id"], "phase": journal["phase"]})
        (self.root / "pending.json").unlink()
        common.durable_tree(self.root)

    def recover(self, *, outcome_confirmed=False, stop_only=False):
        require(outcome_confirmed, "Confirm the prior host unit and Docker mutation are no longer active")
        journal = common.read(self.root / "pending.json")
        candidate, previous = journal["candidate"], journal["previous"]
        restarting = bool(previous and not previous.get("disabled"))
        require(stop_only != restarting,
                "Choose explicit stop-only recovery when there is no active previous generation")
        require(companions() == journal["companions"] and topology() == journal["networks"], "Host changed; inspect recovery evidence")
        directory = self.directory(previous or candidate)
        self.ownership([candidate, previous], strict_limits=False)
        if restarting:
            preflight(previous["images"], self.scanner, self.cache)
            self.compose(directory, "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "egress", "gateway")
            self.ready()
            self.ownership([previous])
        else:
            self.compose(self.directory(candidate), "stop", "gateway", "egress")
        restored = dict(previous or candidate, runtime=runtime(), disabled=not previous or previous.get("disabled", False))
        require(companions() == journal["companions"] and topology(require_app=not restored["disabled"]) == journal["networks"], "Recovery changed unrelated state")
        self.save(restored)
        journal["phase"] = "recovered"
        self.finish(journal)

    def disable(self, *, outcome_confirmed=False):
        """Contain accepted services without starting/scanning any image."""
        require(outcome_confirmed and not (self.root / "pending.json").exists(), "Use explicit pending recovery first")
        current = self.current()
        require(current is not None, "No accepted app release")
        journal = {"id": uuid.uuid4().hex, "phase": "stop-only", "candidate": current, "previous": None,
                   "companions": companions(), "networks": topology(require_app=not current.get("disabled"))}
        common.atomic(self.root / "pending.json", journal)
        self.recover(outcome_confirmed=True, stop_only=True)

    def rollback(self, *, outcome_confirmed=False):
        require(outcome_confirmed and not (self.root / "pending.json").exists(), "Use explicit pending recovery first")
        current = self.current()
        require(current is not None, "No accepted app release")
        previous_id = current.get("previous")
        previous = None
        if previous_id:
            require(re.fullmatch(r"[a-f0-9]{40}-[a-f0-9]{32}", previous_id), "Invalid previous release identity")
            previous = common.read(self.root / "records" / (previous_id + ".json"))
            self.directory(previous)
        require(previous and not previous.get("disabled"),
                "No active previous generation; use explicit disable for stop-only containment")
        journal = {"id": uuid.uuid4().hex, "phase": "rollback", "candidate": current, "previous": previous,
                   "companions": companions(), "networks": topology(require_app=not current.get("disabled"))}
        common.atomic(self.root / "pending.json", journal)
        self.recover(outcome_confirmed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("stage", "promote", "deploy", "recover", "rollback", "disable"))
    parser.add_argument("--id")
    parser.add_argument("--source")
    parser.add_argument("--gateway")
    parser.add_argument("--egress")
    parser.add_argument("--secrets", type=Path)
    parser.add_argument("--scanner", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--initial", action="store_true")
    parser.add_argument("--confirm-stopped-attempt", action="store_true")
    parser.add_argument("--stop-only", action="store_true", help="Recover to stopped services; never start an image")
    args = parser.parse_args()
    require(not args.stop_only or args.operation == "recover", "Stop-only applies only to pending recovery")
    require(os.name == "posix" and os.geteuid() == 0, "Use the separately authorized Linux operator")
    require(re.fullmatch(r"[a-f0-9]{32}", os.environ.get("INVOCATION_ID", "")), "Run in the authorized persistent systemd unit")
    require(os.environ.get("DOCKER_HOST", "") in {"", "unix:///var/run/docker.sock", "unix:///run/docker.sock"}, "Local Docker daemon required")
    context = json.loads(common.docker("context", "inspect"))[0]
    require(context["Endpoints"]["docker"]["Host"] in {"unix:///var/run/docker.sock", "unix:///run/docker.sock"}, "Local Docker context required")
    os.umask(0o077)
    with locks():
        release = Release(scanner=args.scanner, cache=args.cache)
        if args.operation in {"deploy", "stage"}:
            require(args.source and args.gateway and args.egress and args.secrets, "Missing deployment inputs")
            inputs = (args.source, {"gateway": args.gateway, "egress": args.egress}, {name: args.secrets / name for name in SECRET_NAMES})
            if args.operation == "stage":
                identity = release.stage_only(*inputs)
                print("Staged YNAB candidate: " + identity)
            else:
                release.deploy(*inputs, initial=args.initial)
        elif args.operation == "promote":
            require(args.id, "Staged candidate identity required")
            release.promote(args.id, initial=args.initial)
        elif args.operation == "recover":
            release.recover(outcome_confirmed=args.confirm_stopped_attempt, stop_only=args.stop_only)
        else:
            getattr(release, args.operation)(outcome_confirmed=args.confirm_stopped_attempt)
    print("YNAB operation completed; private release evidence retained")


if __name__ == "__main__":
    try:
        main()
    except (common.ReleaseError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit("YNAB operation blocked/failed; inspect private journal; do not retry past a pending barrier") from None
