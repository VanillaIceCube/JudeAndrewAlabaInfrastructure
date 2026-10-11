# 🚦 Operator cutover and reversal

Architecture v2 was [approved by the owner](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6111586759).
These are candidate commands for Agent 3's **separately approved production plan**.
Do not execute merely because code is merged. Agent 3 must insert exact approved
commits, maintenance time, credential/backup evidence and acceptance operators
in the plan on #4. Both already-running apps share the brief gateway outage.

Navigation: [conditions](#conditions-before-a-production-plan) ·
[private prerequisites](#private-prerequisites-only-within-authorized-preparation) ·
[capture](#capture-and-validate-under-the-release-hold) ·
[transfer/reversal](#transfer-and-immediate-reversal) ·
[app activation](#activate-app-only-releases-sequentially).

This is the one-time ingress migration runbook. `scripts/snapshot_sqlite.py`
provides cutover-only backup/restore evidence while legacy apps are running;
it is not a scheduled backup system or a second app release mechanism.
Subsequent app releases use their canonical production guides and the
[shared release standard](app-release-standard.md).

## Conditions before a production plan

- All three primary implementation PRs separately approved and merged; hold
  both legacy app Deploy workflows, queued/in-flight uploads and manual work.
  Agent 3 must name the hold mechanism and verify no active jobs before capture.
  Do not dispatch either workflow or promote `env-prod` during preparation.
- Inventory hostname/apex routing and port-3000 consumers. This implementation
  preserves Notoli as the first/default vhost and its existing port 3000. It
  does not invent apex website routing or silently retire the direct listener.
- Record `docker compose version`, network IDs/members/IPAM, exact app/gateway
  image IDs/digests, mounts and current config. Never dump environment values
  into tickets or terminal logs. Preserve private raw evidence on the host.
- Verify Cloudflare Full (strict), origin access, cache/challenge exemptions for
  MCP/discovery/auth; current certificate SAN/expiry and private key access.
- Establish representative capacity, image/backup disk budget and release
  concurrency policy. The code checks 512 MiB memory and 20% disk with recovery
  allowance, but that does not measure peak load. Initially serialize app
  releases operationally until concurrent-load evidence exists.
- Obtain consistent SQLite snapshots and isolated restore checks for both apps
  under the approved hold/writer-stop procedure, preserving file ownership.
  Approve encrypted off-host destination, access, retention and recovery owner.
  Do not claim off-host protection from a local file or integrity check alone.
- Record both apps' baseline login/API behavior and Notoli discovery, challenge,
  OAuth consent and actual MCP behavior. Any accounts/mail/AI/write tests need
  explicit scope. Pin command expectations and failure cutoff in the plan.

## Private prerequisites (only within authorized preparation)

The initial operator is root, matching current access to `/root/apps/notoli` and
the root-owned MacroMapper directory. A different identity needs a separately
reviewed ownership/sudo arrangement. Do not blindly chown live data or keys.

```bash
umask 077
install -d -m 0700 /var/lib/jude-deploy-locks
# Create once: never replace/unlink these lock inodes during releases.
for name in maintenance notoli macromapper; do
  test ! -e "/var/lib/jude-deploy-locks/$name.lock"
  ( set -C; : > "/var/lib/jude-deploy-locks/$name.lock" )
done
chmod 0600 /var/lib/jude-deploy-locks/*.lock
```

For repeat preparation, verify existing files are regular, root-owned 0600 in
the root-owned 0700 directory instead of rerunning creation. App root directories
and their `incoming`, `releases`, `recovery` children must be owned by the chosen
identity and 0700. Changing existing Notoli directory mode is an explicit plan
step after consumer review; it is never done silently by app CI. Neither this
step nor staging removes/replaces `db.sqlite3`, certificates or current configs.

Place the approved infrastructure checkout at `/opt/host-ingress`. Keep its Git
commit fixed and files root-owned. Preserve `/root/apps/notoli/certs` initially;
its key remains 0600 with the observed owner and current root Nginx master.
Set/verify CI `DEPLOY_HOST_FINGERPRINT` and GHCR pull credentials privately.

## Capture and validate under the release hold

Use one shell for the full maintenance operation. Both new app scripts acquire
this lock shared, followed by their exclusive app lock; this operator takes it
exclusive. Old workflows do not acquire it, so the release hold is also required.

```bash
set -euo pipefail
umask 077
exec 9<>/var/lib/jude-deploy-locks/maintenance.lock
flock -n -x 9
cd /opt/host-ingress
python3 scripts/check_host.py legacy
docker compose -p host-ingress -f compose.yml config --quiet
recovery="/opt/host-ingress-recovery/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 /opt/host-ingress-recovery
mkdir -m 0700 "$recovery"
# The directory must be a new capture; final artifact matching occurs under hold.
cp -p /root/apps/notoli/docker-compose.yml "$recovery/notoli-base.yml"
cp -p /root/apps/notoli/docker-compose.override.yml "$recovery/notoli-override.yml"
cp -p /root/apps/notoli/.env "$recovery/notoli.env"
cp -p /root/apps/notoli/nginx-proxy.conf "$recovery/notoli-vhost.conf"
cp -p /opt/apps/macromapper/nginx-shared.conf "$recovery/macromapper-vhost.conf"
docker inspect notoli-proxy > "$recovery/proxy-private.json"
docker image inspect nginx@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2 > "$recovery/image.json"
chmod 0600 "$recovery"/*
```

The full proxy inspection contains environment data: keep it private. Capture
and verify DB snapshots, app configs/env/image identities and their matching
release records in the same hold as described above; Agent 3 must include the
exact snapshot/restore choices in the approved plan. The following captures
consistent SQLite snapshots inside each running backend namespace, including
container-local WAL, with isolated restore checks (60-second copy budget)
without replacing either live DB. It creates/removes one private `/tmp` snapshot
inside each container and copies it to the private recovery directory; this
is an explicit approved preparation action. Errors stop preparation and no verified marker
is written. Run under the same hold, after recording both app identities:

```bash
python3 scripts/snapshot_sqlite.py notoli-backend "$recovery/notoli-data"
python3 scripts/snapshot_sqlite.py macromapper-backend "$recovery/macromapper-data"
```

Do not substitute a host-only backup of the single bind-mounted DB file: its
WAL/rollback journal can be inside the container. A backend that cannot run the
snapshot helper requires an approved stopped-container DB/journal capture using
the app recovery tool before any recreation. The helper records source ownership/mode and snapshot checksum privately.
App rollback restores through each app's production release tool; gateway-only
reversal does not restore data. Off-host copy/retention remains a separately
specified operator step. Do not proceed with an
unverified or incomplete recovery set.

Prepare a proxy-only recovery model with **original** project-directory/env
resolution. Keep live source paths intact throughout cutover; captured files
are not interpreted relative to the recovery directory.

```bash
docker compose --project-directory /root/apps/notoli --env-file "$recovery/notoli.env" \
  -p notoli -f "$recovery/notoli-base.yml" -f "$recovery/notoli-override.yml" \
  config --format json > "$recovery/legacy-expanded-private.json"
python3 - "$recovery" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
m = json.loads((p/'legacy-expanded-private.json').read_text())
s = m['services']['proxy']
runtime = json.loads((p/'proxy-private.json').read_text())[0]
image = json.loads((p/'image.json').read_text())[0]
if runtime['Image'] != image['Id']:
    raise SystemExit('Cached digest no longer matches running legacy proxy')
if runtime['HostConfig']['RestartPolicy']['Name'] != 'always':
    raise SystemExit('Legacy restart policy drift requires review')
s['image'] = 'nginx@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2'
s.pop('depends_on', None)
m['services'] = {'proxy': s}
names = {'default':'notoli_default', 'backend_private':'notoli_backend_private', 'ingress':'macromapper-ingress'}
assert set(s['networks']) == set(names)
m['networks'] = {k:{'name':v, 'external':True} for k,v in names.items()}
mounts = {v['target']:v['source'] for v in s['volumes']}
assert mounts == {'/etc/nginx/conf.d/default.conf':'/root/apps/notoli/nginx-proxy.conf',
                  '/etc/nginx/conf.d/macromapper.conf':'/opt/apps/macromapper/nginx-shared.conf',
                  '/etc/nginx/certs':'/root/apps/notoli/certs'}
assert s['networks']['backend_private']['ipv4_address'] == '172.30.88.2'
(p/'legacy-proxy.json').write_text(json.dumps(m))
PY
docker compose -p notoli -f "$recovery/legacy-proxy.json" config --quiet
```

Syntax-check with no live network/ports; a Compose one-off would compete for `.2`.

```bash
docker run --rm --network none \
  --mount type=bind,src=/opt/host-ingress/nginx/nginx.conf,dst=/etc/nginx/nginx.conf,readonly \
  --mount type=bind,src=/opt/host-ingress/nginx/vhosts,dst=/etc/nginx/conf.d,readonly \
  --mount type=bind,src=/opt/host-ingress/nginx/snippets,dst=/etc/nginx/snippets,readonly \
  --mount type=bind,src=/root/apps/notoli/certs,dst=/etc/nginx/certs,readonly \
  nginx@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2 nginx -t
```

## Transfer and immediate reversal

Only after all conditions pass and Agent 3 has explicit cutover approval:

```bash
docker update --restart=no notoli-proxy
docker stop notoli-proxy
docker rm notoli-proxy
python3 scripts/check_host.py vacant
# Also inspect ss -lnt to confirm :80/:443 vacancy; unexpected ownership stops work.
docker compose -p host-ingress -f compose.yml up -d --no-deps --pull never proxy
python3 scripts/check_host.py host
```

Do not use `down`, `--remove-orphans`, a mutable image pull, network recreation,
or whole-project app startup. Verify **both** HTTPS vhosts, direct Django routes,
Notoli discovery and 401 MCP challenge immediately, then approved functional
acceptance. On failure at the pre-approved cutoff, reverse while the hold and
exclusive lock are retained:

```bash
docker stop host-ingress-proxy
docker rm host-ingress-proxy
python3 scripts/check_host.py vacant
# Verify original live vhost files match their captures (restore only if altered).
cmp /root/apps/notoli/nginx-proxy.conf "$recovery/notoli-vhost.conf"
cmp /opt/apps/macromapper/nginx-shared.conf "$recovery/macromapper-vhost.conf"
docker compose -p notoli -f "$recovery/legacy-proxy.json" \
  up -d --no-deps --pull never proxy
python3 scripts/check_host.py legacy
```

If replacement creation failed before a container exists, inspect and skip its
stop/removal; never let an assumed container state prevent the approved reversal.
Confirm restored restart policy and both apps. Proxy-only reversal never restores
an app DB. Preserve all app containers, network IDs, certificates and data.

## Activate app-only releases, sequentially

After gateway acceptance, deploy the approved Notoli implementation through its
new pipeline and validate MCP/OAuth and an independent repeat release. Then do
MacroMapper. Those actions require their own approved release plan and must not
run under this exclusive lock. End maintenance only when the approved hold
transition makes it safe. Each app takes shared host + exclusive app locks.

Record before/after ingress and other-app container IDs/start times/image IDs,
network IDs, route checks, retained recovery identities and actual image digests.
App rollback uses each new app release tool, never a preserved legacy deploy
script. Preserve old bridge files until recovery is proven; retire them later
through a specifically authorized cleanup. Reboot, off-host restore, email and
AI tests are explicit later acceptance operations, not implied by green CI.
