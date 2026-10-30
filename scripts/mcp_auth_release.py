"""Private, owner-operated single-container MCP authorization release transaction.

No ingress, network, provider, application-release framework or credential
provisioning is owned here. A failed/ambiguous mutation leaves a durable barrier.
Database recovery is explicit; restoring old grants requires route containment
and revocation before a service can become accepted again.
"""
import argparse
from contextlib import contextmanager, closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time
import uuid

import gateway_release as common
from snapshot_sqlite import capture

ROOT = Path('/opt/mcp-auth-deploy')
REPO = Path(__file__).resolve().parents[1]
IMAGE = re.compile(r'ghcr\.io/vanillaicecube/judeandrewalabainfrastructure-mcp-auth@sha256:[a-f0-9]{64}')
PROJECT, SERVICE, NAME = 'mcp-auth', 'authorization', 'mcp-auth-server'
NETWORK, ADDRESS = 'mcp_auth_private', '172.30.92.3'
SUBNET, GATEWAY = '172.30.92.0/29', '172.30.92.1'
TASK_LABEL = 'io.jude.mcp-auth.task'
KEYS = ('django_secret_key', 'signing_key.pem')
REVOKED_TABLES = ('oauth2_provider_accesstoken', 'oauth2_provider_refreshtoken',
                  'oauth2_provider_grant', 'django_session')
MANAGEMENT_TMPFS = {'/tmp': 'rw,noexec,nosuid,size=16777216,mode=1777'}
require = common.require


def preflight(image, scanner, cache):
    # Mandatory production gates, not configurable approval files or callbacks.
    from preflight_mcp_auth_release import preflight as verify
    return verify(image, scanner, cache)


def baseline():
    from mcp_auth_containment import baseline as inspect_baseline
    return inspect_baseline()


def require_contained():
    from mcp_auth_containment import require_contained as verify
    return verify()


@contextmanager
def locks(directory=common.LOCK.parent):
    with common.maintenance(directory / 'maintenance.lock', shared=True):
        with common.maintenance(directory / 'mcp-auth.lock'):
            yield


def identity(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'Symlinked release evidence')
        if path.is_file():
            info = common.regular(path).stat()
            result[str(path.relative_to(directory))] = [info.st_uid, info.st_gid,
                stat.S_IMODE(info.st_mode), hashlib.sha256(path.read_bytes()).hexdigest()]
    return result


def sync_directories(*paths):
    for path in paths:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def directory_inode(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode), 'Expected an unaliased database directory')
    return [info.st_dev, info.st_ino]


def source_bytes(source):
    require(common.SHA.fullmatch(source), 'Full reviewed source commit required')
    require(common.run(['git', '-C', REPO, 'rev-parse', 'HEAD']).strip() == source,
            'Use the exact reviewed checkout')
    require(not common.run(['git', '-C', REPO, 'status', '--porcelain']).strip(),
            'Reviewed source checkout must be clean')
    return common.run(['git', '-C', REPO, 'show', source + ':services/mcp-auth/compose.yml'])


def topology(*, require_app=False):
    network = common.inspect('network', NETWORK)
    configs = network.get('IPAM', {}).get('Config') or []
    require(network['Driver'] == 'bridge' and network['Internal'] is True
            and not network.get('EnableIPv6') and len(configs) == 1,
            'Authorization network policy drift')
    config = configs[0]
    require(set(config) <= {'Subnet', 'Gateway', 'IPRange'} and config.get('IPRange', '') == ''
            and config.get('Subnet') == SUBNET and config.get('Gateway') == GATEWAY,
            'Authorization network IPAM drift')
    allowed = {NAME: ADDRESS, 'host-ingress-proxy': '172.30.92.2'}
    members = {member['Name']: member['IPv4Address'].split('/')[0]
               for member in (network.get('Containers') or {}).values()}
    require(set(members) <= set(allowed) and all(allowed[name] == ip for name, ip in members.items()),
            'Unexpected authorization network endpoint')
    if require_app:
        require(members.get(NAME) == ADDRESS, 'Missing authorization endpoint')
    return network['Id']


def runtime():
    ids = set(common.docker('ps', '-aq', '--filter', 'label=com.docker.compose.project=' + PROJECT).split())
    ids.update(common.docker('ps', '-aq', '--filter', 'name=^/' + NAME + '$').split())
    require(len(ids) <= 1, 'Unexpected authorization project members')
    if not ids:
        return None
    value = common.inspect('container', ids.pop())
    labels = value['Config'].get('Labels') or {}
    require(value['Name'] == '/' + NAME and labels.get('com.docker.compose.project') == PROJECT
            and labels.get('com.docker.compose.service') == SERVICE, 'Unmanaged authorization container')
    value['Mounts'] = sorted(value['Mounts'], key=lambda mount: mount['Destination'])
    result = {key: value[key] for key in ('Id', 'Image', 'Config', 'HostConfig', 'Mounts')}
    result.update(running=value['State']['Running'], started=value['State']['StartedAt'],
        networks={name: item['IPAddress'] for name, item in value['NetworkSettings']['Networks'].items()},
        aliases={name: sorted(item.get('Aliases') or []) for name, item in value['NetworkSettings']['Networks'].items()})
    return result


def protected_host(host, expected, mounts=(), *, management=False):
    """Closed runtime policy shared by the sole service and short-lived writer."""
    tmpfs = MANAGEMENT_TMPFS if management else dict(item.split(':', 1) for item in expected.get('tmpfs', []))
    require(host.get('ReadonlyRootfs') and not host.get('Privileged') and not host.get('PortBindings')
            and not host.get('PublishAllPorts') and set(host.get('CapDrop') or []) == {'ALL'}
            and not host.get('CapAdd') and host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true'])
            and (host.get('Tmpfs') or {}) == tmpfs
            and all(item.get('Type') == 'bind' for item in host.get('Mounts') or [])
            and all(item['Type'] == 'bind' or (item['Type'] == 'tmpfs'
                and item['Destination'] in tmpfs and item['RW']) for item in mounts)
            and not any(host.get(key) for key in ('Devices', 'DeviceRequests', 'DeviceCgroupRules',
                'VolumesFrom', 'Links', 'GroupAdd', 'ExtraHosts', 'Dns', 'DnsOptions', 'DnsSearch', 'Sysctls'))
            and host.get('PidMode', '') == '' and host.get('IpcMode', 'private') == 'private'
            and host.get('UTSMode', '') == '' and host.get('UsernsMode', '') == ''
            and host.get('Runtime', 'runc') in {'', 'runc'}
            and not host.get('OomKillDisable') and host.get('LogConfig', {}).get('Type') == 'none'
            and host.get('Memory') == expected['mem_limit'] and host.get('PidsLimit') == expected['pids_limit']
            and host.get('NanoCpus', 0) == round(float(expected.get('cpus', 0.5 if management else 0)) * 1e9)
            and host.get('RestartPolicy', {}).get('Name') == 'no'
            and bool(host.get('Init')) == (True if management else bool(expected.get('init'))),
            'Protected authorization runtime policy mismatch')


class Release:
    def __init__(self, root=ROOT, scanner=None, cache=None):
        self.root, self.scanner, self.cache = root, scanner, cache
        common.private(root)
        for name in ('releases', 'records', 'attempts', 'recovery', 'diagnostics'):
            (root / name).mkdir(mode=0o700, exist_ok=True)
            common.private(root / name)
        common.DIAGNOSTICS = root / 'diagnostics'
        self.data = root / 'data'

    def data_directory(self):
        info = self.data.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 65532 and info.st_gid == 65532
                and stat.S_IMODE(info.st_mode) == 0o700, 'Protected authorization data directory required')
        for path in self.data.iterdir():
            require(path.name in {'db.sqlite3', 'db.sqlite3-wal', 'db.sqlite3-shm', 'db.sqlite3-journal'},
                    'Unexpected authorization data file')
            info = common.regular(path).stat()
            require(info.st_uid == 65532 and info.st_gid == 65532 and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                    'Unsafe authorization database ownership/mode')

    def directory(self, record):
        path = Path(record['directory'])
        require(path.parent == self.root / 'releases' and path.name == record['id']
                and re.fullmatch(r'[a-f0-9]{40}-[a-f0-9]{32}', record['id'])
                and record['source'] == record['id'][:40], 'Invalid matched release identity')
        common.private(path)
        require(identity(path) == record['files'], 'Matched release files changed')
        require(IMAGE.fullmatch(record['image']), 'Unapproved image repository/digest')
        model = common.read(path / 'model.json')
        require(set(model.get('services', {})) == {SERVICE}
                and model['services'][SERVICE].get('image') == record['image'],
                'Release record/model image mismatch')
        return path

    def current(self):
        if not (self.root / 'current.json').exists():
            require(runtime() is None, 'Unmanaged initial authorization service')
            return None
        record = common.read(self.root / 'current.json')
        self.directory(record)
        require(runtime() == record['runtime'], 'Accepted authorization runtime drift')
        return record

    def save(self, record):
        self.directory(record)
        common.atomic(self.root / 'records' / (record['id'] + '.json'), record)
        common.atomic(self.root / 'current.json', record)

    def compose(self, directory, *arguments):
        return common.docker('compose', '-p', PROJECT, '-f', directory / 'model.json', '--profile', 'manual-auth', *arguments)

    def ownership(self, records):
        live = runtime()
        if live is None:
            return
        host = live['HostConfig']
        require(host.get('ReadonlyRootfs') and not host.get('Privileged') and not host.get('PortBindings')
                and set(host.get('CapDrop') or []) == {'ALL'} and not host.get('CapAdd')
                and host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true'])
                and live['Config']['User'] == '65532:65532', 'Unsafe authorization runtime')
        for record in filter(None, records):
            model = common.read(self.directory(record) / 'model.json')
            expected = model['services'][SERVICE]
            protected_host(host, expected, live['Mounts'])
            mounts = {(item['target'], item['source'], not item.get('read_only', False)) for item in expected['volumes']}
            actual = {(item['Destination'], item['Source'], item['RW']) for item in live['Mounts'] if item['Type'] == 'bind'}
            network_ok = (live['networks'] == {NETWORK: ADDRESS} and 'mcp-auth-server' in live['aliases'].get(NETWORK, []))
            if not live['running']:
                network_ok = network_ok or (set(live['networks']) <= {NETWORK} and not any(live['networks'].values()))
            image = common.inspect('image', record['image'])
            live_env = dict(value.split('=', 1) for value in live['Config'].get('Env', []))
            expected_env = dict(value.split('=', 1) for value in image.get('Config', {}).get('Env', []))
            expected_env.update({key: str(value) for key, value in expected.get('environment', {}).items()})
            env_ok = live_env == expected_env
            entrypoint, command = expected.get('entrypoint'), expected.get('command')
            # Compose serializes inherited image defaults as explicit nulls.
            # A non-null entrypoint overrides the image and clears its default CMD.
            if entrypoint is None:
                entrypoint = image.get('Config', {}).get('Entrypoint')
                if command is None:
                    command = image.get('Config', {}).get('Cmd')
            command_ok = (live['Config'].get('Cmd') == command
                and live['Config'].get('Entrypoint') == entrypoint)
            if (live['Image'] == image['Id'] and actual == mounts and network_ok and env_ok and command_ok
                    and all(item['Type'] in {'bind', 'tmpfs'} for item in live['Mounts'])
                    and host.get('Memory') == expected['mem_limit'] and host.get('PidsLimit') == expected['pids_limit']
                    and host.get('NanoCpus', 0) == round(float(expected.get('cpus', 0)) * 1e9)
                    and host.get('RestartPolicy', {}).get('Name') == expected['restart']):
                return
        raise common.ReleaseError('Authorization container differs from matched releases')

    def stage(self, source, image, secrets, key_id):
        require(IMAGE.fullmatch(image) and set(secrets) == set(KEYS), 'Exact image and two protected keys required')
        require(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key_id), 'Explicit signing key identity required')
        recipe = source_bytes(source)
        self.data_directory()
        for path in secrets.values():
            info = common.regular(path).stat()
            require(info.st_uid == 65532 and info.st_gid == 65532 and stat.S_IMODE(info.st_mode) == 0o400,
                    'Input key must be uid65532/gid65532 mode0400')
        directory = self.root / 'releases' / (source + '-' + uuid.uuid4().hex)
        directory.mkdir(mode=0o700)
        (directory / 'compose.yml').write_text(recipe)
        (directory / 'compose.yml').chmod(0o600)
        secret_root = directory / 'secrets'
        secret_root.mkdir(mode=0o700)
        for name, path in secrets.items():
            target = secret_root / name
            shutil.copyfile(path, target)
            os.chown(target, 65532, 65532)
            target.chmod(0o400)
        repository, digest = image.split('@sha256:')
        environment = {key: os.environ[key] for key in ('PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT') if key in os.environ}
        environment.update(MCP_AUTH_REPOSITORY=repository, MCP_AUTH_SHA256=digest,
            MCP_AUTH_DATA_DIRECTORY=str(self.data), MCP_AUTH_DJANGO_SECRET_FILE=str(secret_root / KEYS[0]),
            MCP_AUTH_SIGNING_KEY_FILE=str(secret_root / KEYS[1]), MCP_AUTH_SIGNING_KEY_ID=key_id)
        result = subprocess.run(['docker', 'compose', '--env-file', '/dev/null', '-p', PROJECT, '-f',
            str(directory / 'compose.yml'), '--profile', 'manual-auth', 'config', '--format', 'json'], env=environment,
            capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, 'Canonical authorization Compose failed')
        model = json.loads(result.stdout)
        require(set(model['services']) == {SERVICE}, 'Single authorization service required')
        service = model['services'][SERVICE]
        # Compose serializes byte-valued mem_limit as decimal text; persist a
        # canonical integer so actual Docker Memory can be compared exactly.
        require(type(service.get('mem_limit')) is int or
                (type(service.get('mem_limit')) is str and service['mem_limit'].isdigit()), 'Invalid memory limit')
        service['mem_limit'] = int(service['mem_limit'])
        require(service['image'] == image and service.get('container_name') == NAME and not service.get('ports')
                and service.get('user') == '65532:65532' and service.get('read_only') is True
                and service.get('profiles') == ['manual-auth'],
                'Canonical authorization service safety mismatch')
        require(service.get('init') is True and service.get('restart') == 'no'
                and service.get('mem_limit') == 192 * 1024**2 and service.get('pids_limit') == 64
                and float(service.get('cpus', 0)) == 0.25 and set(service.get('cap_drop', [])) == {'ALL'}
                and service.get('security_opt') == ['no-new-privileges:true']
                and service.get('logging') == {'driver': 'none'}
                and service.get('tmpfs') == ['/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532,mode=0700']
                and service.get('environment') == {'MCP_AUTH_SIGNING_KEY_ID': key_id, 'DJANGO_TRUSTED_PROXY_IPS': '172.30.92.2'}
                and not any(service.get(key) for key in ('privileged', 'cap_add', 'devices', 'device_cgroup_rules',
                    'volumes_from', 'links', 'pid', 'ipc', 'uts', 'userns_mode', 'network_mode', 'entrypoint', 'command',
                    'extra_hosts', 'dns', 'dns_search', 'dns_opt', 'sysctls', 'group_add')),
                'Canonical authorization protected policy mismatch')
        require(set(model['networks']) == {'private'}, 'Single external private network required')
        private = model['networks']['private']
        require(not private.get('ipam'), 'App release cannot own network IPAM')
        private.pop('ipam', None)  # Compose adds an empty object to external networks.
        require(private == {'external': True, 'name': NETWORK}
                and set(service['networks']) == {'private'} and service['networks']['private'].get('ipv4_address') == ADDRESS
                and NAME in service['networks']['private'].get('aliases', []), 'External private network required')
        expected = {('/data', str(self.data), False), ('/run/secrets/django_secret_key', str(secret_root / KEYS[0]), True),
                    ('/run/secrets/signing_key.pem', str(secret_root / KEYS[1]), True)}
        require({(v['target'], v['source'], v.get('read_only', False)) for v in service['volumes']} == expected
                and all(v['type'] == 'bind' for v in service['volumes']), 'Matched data/key binds required')
        common.atomic(directory / 'model.json', model)
        common.durable_tree(directory)
        return {'id': directory.name, 'source': source, 'directory': str(directory), 'image': image,
                'key_id': key_id, 'files': identity(directory)}

    def journal(self, value):
        common.atomic(self.root / 'pending.json', value)

    def writers(self, journal):
        """Reject any other container sharing this writable DB namespace."""
        accepted = {item['id'] for item in journal.get('tasks', []) if item.get('id')}
        live = runtime()
        if live:
            accepted.add(live['Id'])
        # One bounded inspect rather than a race-prone per-container walk.
        # A disappearing unrelated disposable container permits only a new
        # READ-ONLY inventory, never a retry of stop/start/create/remove.
        for attempt in range(3):
            ids = set(common.docker('ps', '-aq', '--no-trunc').split())
            try:
                containers = json.loads(common.docker('container', 'inspect', *sorted(ids))) if ids else []
                require({item['Id'] for item in containers} == ids, 'Incomplete container inventory')
                break
            except common.CommandTimeout:
                raise
            except common.ReleaseError:
                changed = set(common.docker('ps', '-aq', '--no-trunc').split()) != ids
                if not changed or attempt == 2:
                    raise
        data = self.data.resolve()
        state = journal.get('restore_state', {})
        namespaces = [data]
        for name in ('prepared', 'retired'):
            if state.get(name):
                path = Path(state[name])
                require(path.parent == self.root / 'recovery', 'Invalid restore namespace')
                namespaces.append(path)
        protected_ids = {(path.stat().st_dev, path.stat().st_ino)
                         for directory in namespaces for path in
                         (directory, *directory.parents, *(directory.iterdir() if directory.exists() else ()))
                         if path.exists()}
        result = []
        for item in containers:
            shares = False
            for mount in item['Mounts']:
                if mount.get('Type') != 'bind' or not mount.get('RW'):
                    continue
                path = Path(mount['Source']).resolve()
                shares |= path == data or path in data.parents or data in path.parents
                if path.exists():
                    info = path.stat()
                    shares |= (info.st_dev, info.st_ino) in protected_ids
            if shares:
                require(item['Id'] in accepted, 'Untracked authorization database writer')
                result.append(item)
        return result

    def stop_writers(self, journal):
        self.ownership([journal.get('previous'), journal['candidate']])
        for item in self.writers(journal):
            if item['State']['Running']:
                common.docker('stop', '--time', '10', item['Id'], timeout=20)
            require(not common.inspect('container', item['Id'])['State']['Running'], 'Writer stop not established')
        require(not any(item['State']['Running'] for item in self.writers(journal)), 'Writer still running')

    def snapshot(self, journal, label):
        """Replay only an isolated copy; retain original journal evidence."""
        require(not any(item['State']['Running'] for item in self.writers(journal)), 'Snapshot requires stopped writers')
        self.data_directory()
        source = self.data / 'db.sqlite3'
        if not source.exists():
            require(not any(self.data.iterdir()), 'Missing main database with journal evidence')
            return None
        evidence = self.root / 'recovery' / (journal['id'] + '-' + label + '-' + uuid.uuid4().hex)
        evidence.mkdir(mode=0o700)
        isolated = evidence / 'writer-copy'
        isolated.mkdir(mode=0o700)
        for suffix in ('', '-wal', '-journal'):
            original = self.data / ('db.sqlite3' + suffix)
            if original.exists():
                shutil.copyfile(common.regular(original), isolated / original.name)
                (isolated / original.name).chmod(0o600)
        # Preserve the stopped writer bytes as evidence. Replay uses a second
        # isolated namespace because SQLite may remove its hot journal/WAL.
        replay = evidence / 'replay'
        replay.mkdir(mode=0o700)
        for path in isolated.iterdir():
            shutil.copyfile(path, replay / path.name)
            (replay / path.name).chmod(0o600)
        with closing(sqlite3.connect(replay / 'db.sqlite3', timeout=5)) as db:
            require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Isolated writer integrity failed')
            db.execute('PRAGMA journal_mode=DELETE')
        metadata = capture(replay / 'db.sqlite3', evidence / 'verified')
        common.atomic(evidence / 'provenance.json', {'writers': [{ 'id': item['Id'], 'started': item['State']['StartedAt']}
            for item in self.writers(journal)], 'database_namespace': str(self.data), 'metadata': metadata})
        common.durable_tree(evidence)
        return {'directory': str(evidence), 'files': identity(evidence), 'sha256': metadata['sha256']}

    def restore(self, journal, recovery):
        require_contained()
        require(recovery is not None, 'No verified pre-migration database to restore')
        evidence = Path(recovery['directory'])
        require(evidence.parent == self.root / 'recovery' and identity(evidence) == recovery['files'], 'Changed recovery evidence')
        source = common.regular(evidence / 'verified' / 'db.sqlite3')
        require(hashlib.sha256(source.read_bytes()).hexdigest() == recovery['sha256'], 'Recovery database mismatch')
        require(not any(item['State']['Running'] for item in self.writers(journal)), 'Restore requires stopped writers')
        # Offline YNAB JWTs survive DB grant deletion until their maximum TTL.
        # This independent monotonic barrier outlives release/rollback records.
        self.quarantine()
        state = journal.get('restore_state')
        if state is None:
            self.data_directory()
            prepared = self.root / 'recovery' / (journal['id'] + '-prepared-' + uuid.uuid4().hex)
            retired = self.root / 'recovery' / (journal['id'] + '-retired-' + uuid.uuid4().hex)
            prepared.mkdir(mode=0o700)
            os.chown(prepared, 65532, 65532)
            target = prepared / 'db.sqlite3'
            shutil.copyfile(source, target)
            os.chown(target, 65532, 65532)
            target.chmod(0o600)
            common.durable_tree(prepared)
            state = {'prepared': str(prepared), 'retired': str(retired), 'phase': 'prepared',
                     'old_inode': directory_inode(self.data), 'new_inode': directory_inode(prepared)}
            # Immutable checkpoint + both namespace identities are durable BEFORE
            # either directory is renamed. Main/WAL/journal retire together.
            journal.update(phase='restoring', checkpoint=recovery, restore_state=state,
                           revocation_required=True, revoked=False)
            self.journal(journal)
        require(journal.get('checkpoint') == recovery and journal.get('revocation_required'),
                'Restore checkpoint/provenance mismatch')
        self.resume_restore(journal)

    def resume_restore(self, journal):
        state = journal['restore_state']
        require(set(state) == {'prepared', 'retired', 'phase', 'old_inode', 'new_inode'}
                and state['phase'] in {'prepared', 'retired', 'complete'}, 'Malformed restore state')
        prepared, retired = Path(state['prepared']), Path(state['retired'])
        for path, role in ((prepared, 'prepared'), (retired, 'retired')):
            require(path.parent == self.root / 'recovery' and
                    re.fullmatch(journal['id'] + '-' + role + r'-[a-f0-9]{32}', path.name), 'Invalid restore namespace')
        # Inspect identities, not just the last phase: a process can die after
        # rename succeeds but before its acknowledgement is journaled.
        if not retired.exists():
            require(directory_inode(self.data) == state['old_inode'] and
                    directory_inode(prepared) == state['new_inode'], 'Original restore namespace drift')
            os.replace(self.data, retired)
            sync_directories(self.root, retired.parent)
        require(directory_inode(retired) == state['old_inode'], 'Retired writer namespace drift')
        state['phase'] = 'retired'
        self.journal(journal)
        if prepared.exists():
            require(not self.data.exists() and directory_inode(prepared) == state['new_inode'],
                    'Prepared restore namespace drift')
            require(set(path.name for path in prepared.iterdir()) == {'db.sqlite3'} and
                    hashlib.sha256(common.regular(prepared / 'db.sqlite3').read_bytes()).hexdigest()
                    == journal['checkpoint']['sha256'], 'Prepared database mismatch')
            os.replace(prepared, self.data)
            sync_directories(self.root, prepared.parent)
        require(directory_inode(self.data) == state['new_inode'], 'Restored writer namespace drift')
        self.data_directory()
        state['phase'] = 'complete'
        journal['revoked'] = False
        self.journal(journal)

    def quarantine(self):
        path = self.root / 'ynab-jwt-quarantine.json'
        previous = 0
        if path.exists() or path.is_symlink():
            info = common.regular(path).stat()
            require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
                    'Unsafe YNAB JWT quarantine record')
            record = common.read(path)
            require(set(record) == {'version', 'not_before'} and type(record['version']) is int
                    and record['version'] == 1 and type(record['not_before']) is int and record['not_before'] >= 0,
                    'Malformed YNAB JWT quarantine record')
            previous = record['not_before']
        value = {'version': 1, 'not_before': max(previous, math.ceil(time.time()) + 905)}
        common.atomic(path, value)
        return value

    def management(self, record, journal, command, *arguments):
        """Create, record exact writer ID, then start once; never retry ambiguity."""
        model = common.read(self.directory(record) / 'model.json')['services'][SERVICE]
        task = {'name': 'mcp-auth-task-' + uuid.uuid4().hex, 'command': command, 'arguments': list(arguments),
                'record': record['id'], 'id': None, 'finished': False}
        journal.setdefault('tasks', []).append(task)
        self.journal(journal)
        args = ['create', '--name', task['name'], '--label', TASK_LABEL + '=1', '--label',
            'io.jude.mcp-auth.attempt=' + journal['id'], '--network', 'none', '--user', '65532:65532',
            '--read-only', '--init', '--log-driver', 'none', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--memory', str(model['mem_limit']), '--cpus', str(model.get('cpus', 0.5)),
            '--pids-limit', str(model['pids_limit']), '--tmpfs', '/tmp:rw,noexec,nosuid,size=16777216,mode=1777']
        for key, value in sorted(model.get('environment', {}).items()):
            args += ['--env', key + '=' + str(value)]
        for mount in model['volumes']:
            args += ['--mount', 'type=bind,src=' + mount['source'] + ',dst=' + mount['target'] +
                     (',readonly' if mount.get('read_only', False) else '')]
        args += ['--entrypoint', '/usr/local/bin/python', record['image'], '/app/manage.py', command, *arguments]
        common.docker(*args, timeout=30)
        created = common.inspect('container', task['name'])
        task['id'] = created['Id']
        self.journal(journal)
        require(not created['State']['Running'], 'Management writer already running')
        self.task_identity(created, record, journal, task)
        self.start_management(task['id'])
        ended = common.inspect('container', task['id'])
        require(not ended['State']['Running'] and ended['State']['ExitCode'] == 0, 'Management command failed')
        task['finished'] = True
        self.journal(journal)
        common.docker('rm', task['id'], timeout=20)
        task['removed'] = True
        self.journal(journal)

    def start_management(self, container_id):
        """Retain successful Django policy warnings privately, not just errors."""
        try:
            result = subprocess.run(['docker', 'start', '-a', container_id], capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired as error:
            def output(value):
                return (value.decode('utf-8', 'replace') if isinstance(value, bytes) else value or '')[-8192:]
            common.atomic(self.root / 'diagnostics' / (uuid.uuid4().hex + '.json'),
                {'container': container_id, 'ambiguous_timeout': True,
                 'stdout': output(error.stdout), 'stderr': output(error.stderr)})
            raise common.CommandTimeout('Management start deadline exceeded; outcome must be inspected') from None
        common.atomic(self.root / 'diagnostics' / (uuid.uuid4().hex + '.json'),
            {'container': container_id, 'exit': result.returncode, 'stdout': result.stdout[-8192:], 'stderr': result.stderr[-8192:]})
        require(result.returncode == 0, 'Management start failed; inspect private evidence')

    def task_identity(self, created, record, journal, task):
        model = common.read(self.directory(record) / 'model.json')['services'][SERVICE]
        expected_binds = {(mount['target'], mount['source'], not mount.get('read_only', False)) for mount in model['volumes']}
        actual_binds = {(mount['Destination'], mount['Source'], mount['RW']) for mount in created['Mounts'] if mount['Type'] == 'bind'}
        host = created['HostConfig']
        protected_host(host, model, created['Mounts'], management=True)
        image = common.inspect('image', record['image'])
        expected_env = dict(value.split('=', 1) for value in image.get('Config', {}).get('Env', []))
        expected_env.update({key: str(value) for key, value in model.get('environment', {}).items()})
        actual_env = dict(value.split('=', 1) for value in created['Config'].get('Env', []))
        require(created['Name'] == '/' + task['name'] and created['Image'] == image['Id']
                and created['Config']['User'] == '65532:65532'
                and created['Config']['Labels'].get(TASK_LABEL) == '1'
                and created['Config']['Labels'].get('io.jude.mcp-auth.attempt') == journal['id']
                and created['Config'].get('Entrypoint') == ['/usr/local/bin/python']
                and created['Config'].get('Cmd') == ['/app/manage.py', task['command'], *task['arguments']]
                and actual_binds == expected_binds and actual_env == expected_env
                and all(mount['Type'] in {'bind', 'tmpfs'} for mount in created['Mounts'])
                and host.get('NetworkMode') == 'none'
                and host.get('ReadonlyRootfs') and not host.get('Privileged') and not host.get('PortBindings')
                and set(host.get('CapDrop') or []) == {'ALL'} and not host.get('CapAdd')
                and host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true'])
                and host.get('Memory') == model['mem_limit'] and host.get('PidsLimit') == model['pids_limit']
                and host.get('NanoCpus', 0) == round(float(model.get('cpus', 0.5)) * 1e9),
                'Management writer identity/policy mismatch')

    def reconcile_tasks(self, journal):
        # Only explicit recovery after the old unit is confirmed stopped may
        # resolve a create whose acknowledgement was lost. Exact name, image,
        # labels, command, mounts and resource policy must all match first.
        for task in journal.get('tasks', []):
            ids = common.docker('ps', '-aq', '--filter', 'name=^/' + task['name'] + '$').split()
            require(len(ids) <= 1, 'Ambiguous management writer name')
            if not ids:
                continue
            require(not task.get('removed'), 'Retired management container reappeared')
            item = common.inspect('container', ids[0])
            require(not task.get('id') or item['Id'] == task['id'], 'Management writer ID changed')
            record = next((record for record in (journal['candidate'], journal.get('previous'))
                           if record and record['id'] == task['record']), None)
            require(record is not None, 'Unknown management release identity')
            self.task_identity(item, record, journal, task)
            task['id'] = item['Id']
            self.journal(journal)

    def cleanup_tasks(self, journal):
        existing = set(common.docker('ps', '-aq', '--no-trunc').split())
        for task in journal.get('tasks', []):
            if task.get('id') in existing:
                require(not common.inspect('container', task['id'])['State']['Running'], 'Management writer still active')
                common.docker('rm', task['id'], timeout=20)
            task['removed'] = True
            self.journal(journal)

    def ready(self):
        program = "import urllib.request\nr=urllib.request.Request('http://127.0.0.1:8000/health/ready',headers={'Host':'172.30.92.3'})\nwith urllib.request.urlopen(r,timeout=5) as response: assert response.status==200"
        for attempt in range(6):
            try:
                require(runtime() and runtime()['running'], 'Authorization service is stopped')
                common.docker('exec', NAME, '/usr/local/bin/python', '-c', program, timeout=10)
                return
            except common.CommandTimeout:
                raise
            except common.ReleaseError:
                if attempt == 5:
                    raise
                time.sleep(1)

    def finish(self, journal):
        require(re.fullmatch(r'[a-f0-9]{32}', journal['id']), 'Invalid attempt identity')
        common.atomic(self.root / 'attempts' / (journal['id'] + '.json'), journal)
        (self.root / 'pending.json').unlink()
        # Includes the parent root fsync without walking the now-running SQLite
        # namespace, where the service may legitimately create/remove journals.
        common.durable_tree(self.root / 'attempts')

    def verify_revoked(self, journal):
        require(not any(item['State']['Running'] for item in self.writers(journal)), 'Revocation check requires stopped writers')
        path = common.regular(self.data / 'db.sqlite3').resolve()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            # These are the pinned Django/DOT table identities, not caller SQL.
            require(all(not db.execute('SELECT EXISTS(SELECT 1 FROM "' + table + '" LIMIT 1)').fetchone()[0]
                        for table in REVOKED_TABLES), 'Restored grants or sessions remain')
        return {'tables': list(REVOKED_TABLES), 'all_empty': True}

    def stage_only(self, source, image, secrets, key_id):
        require(not (self.root / 'pending.json').exists(), 'Pending transaction blocks staging')
        self.current()
        preflight(image, self.scanner, self.cache)
        record = dict(self.stage(source, image, secrets, key_id), staged=True)
        common.atomic(self.root / 'records' / (record['id'] + '.json'), record)
        return record['id']

    def deploy(self, source, image, secrets, key_id, *, initial=False):
        identity = self.stage_only(source, image, secrets, key_id)
        self.promote(identity, initial=initial)

    def promote(self, identity, *, initial=False):
        require(not (self.root / 'pending.json').exists(), 'Pending transaction blocks promotion')
        require(re.fullmatch(r'[a-f0-9]{40}-[a-f0-9]{32}', identity), 'Invalid staged release identity')
        candidate = common.read(self.root / 'records' / (identity + '.json'))
        require(candidate.get('staged') is True and 'runtime' not in candidate, 'Unaccepted staged candidate required')
        self.directory(candidate)
        previous = self.current()
        require(previous is not None or initial, 'Explicit initial operation required')
        # First-rollout policy deliberately contains both routes for the entire
        # migration/recovery window, so rollback cannot expose restored grants.
        require_contained()
        before, network = baseline(), topology(require_app=bool(previous and not previous.get('disabled')))
        preflight(candidate['image'], self.scanner, self.cache)
        self.ownership([previous])
        journal = {'id': uuid.uuid4().hex, 'phase': 'prepared', 'candidate': candidate, 'previous': previous,
                   'baseline': before, 'network': network, 'migration_started': False, 'tasks': []}
        self.journal(journal)
        try:
            self.stop_writers(journal)
            journal['backup'] = self.snapshot(journal, 'before-migration')
            journal.update(phase='migrating', migration_started=True)
            self.journal(journal)  # Before the first possible database writer.
            self.management(candidate, journal, 'migrate', '--noinput')
            self.management(candidate, journal, 'check', '--deploy', '--fail-level', 'ERROR')
            self.management(candidate, journal, 'migrate', '--check')
            journal['phase'] = 'starting'
            self.journal(journal)
            self.compose(self.directory(candidate), 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', SERVICE)
            self.ready()
            self.ownership([candidate])
            require(baseline() == before and topology(require_app=True) == network, 'Unrelated infrastructure changed')
            candidate.update(runtime=runtime(), disabled=False, previous=previous['id'] if previous else None,
                             recovery=journal['backup'])
            candidate.pop('staged', None)
            self.save(candidate)
            journal['phase'] = 'accepted'
            self.journal(journal)
            self.finish(journal)
        except BaseException:
            raise common.ReleaseError('Authorization release failed/interrupted; explicit recovery required') from None

    def recover(self, *, strategy, outcome_confirmed=False):
        require(outcome_confirmed, 'Confirm prior host unit and Docker mutations are no longer active')
        require(strategy in {'keep', 'restore'}, 'Explicit keep or restore strategy required')
        journal = common.read(self.root / 'pending.json')
        candidate, previous = journal['candidate'], journal['previous']
        self.directory(candidate)
        if previous:
            self.directory(previous)
        require(baseline() == journal['baseline'] and topology() == journal['network'], 'Host baseline changed')
        require(strategy != 'keep' or not journal['migration_started'], 'Post-migration keep recovery is not proven compatible')
        if previous and not previous.get('disabled'):
            preflight(previous['image'], self.scanner, self.cache)
        self.reconcile_tasks(journal)
        self.stop_writers(journal)
        # Preserve the failed writer namespace before any explicit replacement.
        if journal.get('restore_state', {}).get('phase') not in {'prepared', 'retired'}:
            rescue = self.snapshot(journal, 'failed-writer')
            journal['rescue'] = rescue
            self.journal(journal)
        else:
            require(journal.get('rescue') is not None, 'Missing pre-restore writer evidence')
        self.cleanup_tasks(journal)
        if not previous or previous.get('disabled'):
            require_contained()
            # No old active service: retain DB and failure evidence, never erase
            # an initially failed migration or pretend it is a clean database.
            restored = dict(previous or candidate, runtime=runtime(), disabled=True, previous=None)
        else:
            if strategy == 'restore':
                self.restore(journal, journal.get('backup'))
                self.management(previous, journal, 'revoke_all_mcp_grants')
                journal['revocation_evidence'] = self.verify_revoked(journal)
                journal.update(revoked=True, phase='revoked')
                self.journal(journal)
                require_contained()
            require(not journal.get('revocation_required') or journal.get('revoked'), 'Restored grants must be revoked')
            self.management(previous, journal, 'check', '--deploy', '--fail-level', 'ERROR')
            self.management(previous, journal, 'migrate', '--check')
            require_contained()
            self.compose(self.directory(previous), 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', SERVICE)
            self.ready()
            self.ownership([previous])
            restored = dict(previous, runtime=runtime(), disabled=False)
        require_contained()
        require(baseline() == journal['baseline'] and topology(require_app=not restored['disabled']) == journal['network'],
                'Recovery changed unrelated state')
        self.save(restored)
        journal.update(phase='recovered', recovery_strategy=strategy)
        self.finish(journal)

    def rollback(self, *, strategy, outcome_confirmed=False):
        require(outcome_confirmed and not (self.root / 'pending.json').exists(), 'Recover pending transaction first')
        require(strategy == 'restore', 'Accepted-release rollback requires contained database restore')
        require_contained()
        current = self.current()
        require(current and current.get('previous'), 'No previous accepted authorization release')
        require(re.fullmatch(r'[a-f0-9]{40}-[a-f0-9]{32}', current['previous']), 'Invalid previous release identity')
        previous = common.read(self.root / 'records' / (current['previous'] + '.json'))
        self.directory(previous)
        journal = {'id': uuid.uuid4().hex, 'phase': 'rollback', 'candidate': current, 'previous': previous,
            'baseline': baseline(), 'network': topology(require_app=True), 'backup': current.get('recovery'),
            'migration_started': True, 'tasks': []}
        self.journal(journal)
        self.recover(strategy=strategy, outcome_confirmed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('stage', 'deploy', 'promote', 'recover', 'rollback'))
    for name in ('id', 'source', 'image', 'key-id'):
        parser.add_argument('--' + name)
    parser.add_argument('--secrets', type=Path)
    parser.add_argument('--scanner', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--initial', action='store_true')
    parser.add_argument('--strategy', choices=('keep', 'restore'))
    parser.add_argument('--confirm-stopped-attempt', action='store_true')
    args = parser.parse_args()
    require(os.name == 'posix' and os.geteuid() == 0, 'Separately authorized Linux root operator required')
    require(re.fullmatch(r'[a-f0-9]{32}', os.environ.get('INVOCATION_ID', '')), 'Persistent authorized systemd unit required')
    require(os.environ.get('DOCKER_HOST', '') in {'', 'unix:///var/run/docker.sock', 'unix:///run/docker.sock'}, 'Local daemon required')
    context = json.loads(common.docker('context', 'inspect'))[0]
    require(context['Endpoints']['docker']['Host'] in {'unix:///var/run/docker.sock', 'unix:///run/docker.sock'}, 'Local context required')
    os.umask(0o077)
    with locks():
        release = Release(scanner=args.scanner, cache=args.cache)
        if args.operation in {'stage', 'deploy'}:
            require(args.source and args.image and args.secrets and args.key_id, 'Missing immutable release inputs')
            inputs = (args.source, args.image, {name: args.secrets / name for name in KEYS}, args.key_id)
            if args.operation == 'stage':
                print('Staged authorization candidate: ' + release.stage_only(*inputs))
            else:
                release.deploy(*inputs, initial=args.initial)
        elif args.operation == 'promote':
            require(args.id, 'Staged identity required')
            release.promote(args.id, initial=args.initial)
        else:
            getattr(release, args.operation)(strategy=args.strategy, outcome_confirmed=args.confirm_stopped_attempt)
    print('Authorization operation complete; private release evidence retained')


if __name__ == '__main__':
    try:
        main()
    except (common.ReleaseError, OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError, sqlite3.Error):
        raise SystemExit('Authorization operation blocked/failed; inspect private evidence and pending barrier') from None
