"""Synthetic providers exercise auth release state and real isolated SQLite recovery.

No production daemon/provider or credentials are contacted. The Linux state
suite executes the real durable/private/flock implementation.
"""
import copy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_auth_release as release

SOURCE, SECOND = 'a' * 40, 'b' * 40


@unittest.skipIf(os.name == 'nt', 'Linux release ownership, directory rename and fsync contract')
class AuthReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mcp-auth-release-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.live, self.events, self.serial = None, [], 0
        self.real_topology = release.topology
        self.app = release.Release(self.root, Path('scanner'), Path('cache'))
        self.app.data.mkdir(mode=0o700)
        self.start(patch.object(self.app, 'data_directory'))
        self.start(patch.object(release, 'runtime', side_effect=lambda: copy.deepcopy(self.live)))
        self.start(patch.object(release, 'baseline', return_value={'five-apps': 'unchanged', 'optional-ynab': 'unchanged'}))
        self.start(patch.object(release, 'topology', return_value='original-network-id'))
        self.start(patch.object(release, 'require_contained', side_effect=lambda: self.events.append('contained')))
        self.start(patch.object(release, 'preflight', side_effect=lambda *a: self.events.append('fresh-scan')))
        self.start(patch.object(self.app, 'stage', side_effect=self.stage))
        self.start(patch.object(self.app, 'ownership'))
        self.start(patch.object(self.app, 'writers', return_value=[]))
        self.start(patch.object(self.app, 'stop_writers', side_effect=self.stop))
        self.start(patch.object(self.app, 'management', side_effect=self.management))
        self.start(patch.object(self.app, 'reconcile_tasks'))
        self.start(patch.object(self.app, 'cleanup_tasks'))
        self.start(patch.object(self.app, 'compose', side_effect=self.compose))
        self.start(patch.object(self.app, 'ready', side_effect=lambda: self.events.append('ready')))

    def start(self, mock):
        value = mock.start()
        self.addCleanup(mock.stop)
        return value

    def image(self, source):
        return 'ghcr.io/vanillaicecube/judeandrewalabainfrastructure-mcp-auth@sha256:' + source[0] * 64

    def stage(self, source, image, secrets, key_id):
        self.events.append('stage')
        directory = self.root / 'releases' / (source + '-' + uuid.uuid4().hex)
        directory.mkdir(mode=0o700)
        release.common.atomic(directory / 'model.json', {'source': source, 'services': {'authorization': {'image': image}}})
        return {'id': directory.name, 'source': source, 'image': image,
                'directory': str(directory), 'key_id': key_id, 'files': release.identity(directory)}

    def stop(self, journal):
        self.assertTrue((self.root / 'pending.json').exists())
        self.events.append('stop')
        if self.live:
            self.live['running'] = False

    def management(self, record, journal, command, *args):
        self.assertTrue((self.root / 'pending.json').exists())
        self.events.append(command + ('-check' if '--check' in args else ''))
        if command == 'check':
            self.assertEqual(args, ('--deploy', '--fail-level', 'ERROR'))
        if command == 'migrate' and '--check' not in args:
            self.assertTrue(release.common.read(self.root / 'pending.json')['migration_started'])
            with closing(sqlite3.connect(self.app.data / 'db.sqlite3')) as db, db:
                db.executescript('CREATE TABLE IF NOT EXISTS grants(value TEXT); CREATE TABLE IF NOT EXISTS sessions(value TEXT);')
                db.execute('INSERT INTO grants VALUES (?)', (record['source'],))
                db.execute('INSERT INTO sessions VALUES (?)', (record['source'],))
                for table in release.REVOKED_TABLES:
                    db.execute('CREATE TABLE IF NOT EXISTS '+table+'(value TEXT)')
                    db.execute('INSERT INTO '+table+' VALUES (?)', (record['source'],))
        elif command == 'revoke_all_mcp_grants':
            self.assertTrue(journal['revocation_required'])
            with closing(sqlite3.connect(self.app.data / 'db.sqlite3')) as db, db:
                db.executescript('DELETE FROM grants; DELETE FROM sessions;')
                for table in release.REVOKED_TABLES:
                    db.execute('DELETE FROM '+table)

    def compose(self, directory, *args):
        self.assertTrue((self.root / 'pending.json').exists())
        self.events.append(args[0])
        if args[0] == 'up':
            self.serial += 1
            self.live = {'Id': str(self.serial), 'running': True,
                         'source': json.loads((directory / 'model.json').read_text())['source']}

    def deploy(self, source=SOURCE, **kwargs):
        return self.app.deploy(source, self.image(source), {}, 'test-key', **kwargs)

    def test_stage_is_inactive_and_promotion_scans_again_before_any_writer(self):
        identity = self.app.stage_only(SOURCE, self.image(SOURCE), {}, 'key')
        self.assertEqual(self.events, ['fresh-scan', 'stage'])
        self.assertIsNone(self.live)
        self.assertFalse((self.root / 'pending.json').exists())
        self.app.promote(identity, initial=True)
        self.assertEqual(self.events[2:5], ['contained', 'fresh-scan', 'stop'])
        self.assertEqual(self.events[-5:], ['migrate', 'check', 'migrate-check', 'up', 'ready'])
        self.assertFalse((self.root / 'pending.json').exists())

    def test_failed_scan_or_uncontained_routes_prevent_all_writer_mutations(self):
        with patch.object(release, 'preflight', side_effect=release.common.ReleaseError('scan')):
            with self.assertRaises(release.common.ReleaseError):
                self.deploy(initial=True)
        self.assertEqual(self.events, [])
        with patch.object(release, 'require_contained', side_effect=release.common.ReleaseError('route')):
            with self.assertRaises(release.common.ReleaseError):
                self.deploy(initial=True)
        self.assertNotIn('stop', self.events)
        self.assertFalse((self.root / 'pending.json').exists())

    def test_upgrade_and_rollback_restore_db_then_revoke_grants_and_sessions(self):
        self.deploy(initial=True)
        first = release.common.read(self.root / 'current.json')
        self.deploy(SECOND)
        self.app.rollback(strategy='restore', outcome_confirmed=True)
        accepted = release.common.read(self.root / 'current.json')
        self.assertEqual(accepted['source'], SOURCE)
        self.assertEqual(accepted['files'], first['files'])
        self.assertLess(self.events.index('revoke_all_mcp_grants'), len(self.events) - 2)
        with closing(sqlite3.connect(self.app.data / 'db.sqlite3')) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM grants').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
        attempts = [release.common.read(path) for path in (self.root / 'attempts').glob('*.json')]
        restored = next(item for item in attempts if item['phase'] == 'recovered')
        self.assertTrue(restored['revoked'])
        self.assertTrue(Path(restored['rescue']['directory']).is_dir())

    def fail_upgrade(self):
        self.deploy(initial=True)
        def fail(record, journal, command, *args):
            self.management(record, journal, command, *args)
            if command == 'migrate' and '--check' not in args:
                raise release.common.CommandTimeout('ambiguous migration')
        with patch.object(self.app, 'management', side_effect=fail):
            with self.assertRaises(release.common.ReleaseError):
                self.deploy(SECOND)

    def test_ambiguous_migration_preserves_barrier_and_never_retries_or_keeps_db(self):
        self.fail_upgrade()
        pending = release.common.read(self.root / 'pending.json')
        self.assertEqual(pending['phase'], 'migrating')
        self.assertTrue(pending['backup'])
        events = list(self.events)
        with self.assertRaises(release.common.ReleaseError):
            self.deploy(SECOND)
        with self.assertRaises(release.common.ReleaseError):
            self.app.recover(strategy='restore')
        with self.assertRaisesRegex(release.common.ReleaseError, 'not proven compatible'):
            self.app.recover(strategy='keep', outcome_confirmed=True)
        self.assertEqual(events, self.events)
        self.app.recover(strategy='restore', outcome_confirmed=True)
        self.assertEqual(release.common.read(self.root / 'current.json')['source'], SOURCE)

    def test_failed_revocation_keeps_restored_database_unaccepted_and_service_stopped(self):
        self.fail_upgrade()
        def fail(record, journal, command, *args):
            if command == 'revoke_all_mcp_grants':
                raise release.common.ReleaseError('revocation failed')
            self.management(record, journal, command, *args)
        before = self.events.count('up')
        with patch.object(self.app, 'management', side_effect=fail), self.assertRaises(release.common.ReleaseError):
            self.app.recover(strategy='restore', outcome_confirmed=True)
        pending = release.common.read(self.root / 'pending.json')
        self.assertTrue(pending['revocation_required'])
        self.assertFalse(pending['revoked'])
        self.assertFalse(self.live['running'])
        self.assertEqual(before, self.events.count('up'))

    def test_noop_revocation_is_detected_before_any_acceptance(self):
        self.fail_upgrade()
        def noop(record, journal, command, *args):
            if command != 'revoke_all_mcp_grants':
                self.management(record, journal, command, *args)
        with patch.object(self.app, 'management', side_effect=noop), self.assertRaisesRegex(release.common.ReleaseError, 'remain'):
            self.app.recover(strategy='restore', outcome_confirmed=True)
        self.assertFalse(self.live['running'])
        self.assertFalse(release.common.read(self.root / 'pending.json')['revoked'])

    def test_staged_record_cannot_scan_one_image_and_start_another(self):
        identity = self.app.stage_only(SOURCE, self.image(SOURCE), {}, 'key')
        path = self.root / 'records' / (identity + '.json')
        record = release.common.read(path)
        record['image'] = self.image(SECOND)
        release.common.atomic(path, record)
        before = list(self.events)
        with self.assertRaisesRegex(release.common.ReleaseError, 'record/model image mismatch'):
            self.app.promote(identity, initial=True)
        self.assertEqual(before, self.events)
        self.assertFalse((self.root / 'pending.json').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX quarantine file mode/ownership')
    def test_quarantine_is_durable_before_replace_and_only_extends_deadline(self):
        self.fail_upgrade()
        real_replace = release.os.replace
        replacements = []
        def replace(source, destination):
            if Path(destination) == self.app.data or Path(source) == self.app.data:
                barrier = release.common.read(self.root / 'ynab-jwt-quarantine.json')
                self.assertGreaterEqual(barrier['not_before'], 1906)
                replacements.append(str(destination))
            return real_replace(source, destination)
        with patch.object(release.time, 'time', return_value=1000.1), patch.object(release.os, 'replace', side_effect=replace):
            self.app.recover(strategy='restore', outcome_confirmed=True)
        self.assertTrue(replacements)
        with patch.object(release.time, 'time', return_value=900.0):
            self.assertEqual(self.app.quarantine()['not_before'], 1906)
        with patch.object(release.time, 'time', return_value=1100.1):
            self.assertEqual(self.app.quarantine()['not_before'], 2006)
        self.assertEqual((self.root / 'ynab-jwt-quarantine.json').stat().st_mode & 0o777, 0o600)

    @unittest.skipIf(os.name == 'nt', 'POSIX quarantine file mode/ownership')
    def test_malformed_quarantine_blocks_restore_before_database_replacement(self):
        self.fail_upgrade()
        path = self.root / 'ynab-jwt-quarantine.json'
        release.common.atomic(path, {'version': 1, 'not_before': True})
        before = (self.app.data / 'db.sqlite3').read_bytes()
        with self.assertRaisesRegex(release.common.ReleaseError, 'Malformed'):
            self.app.recover(strategy='restore', outcome_confirmed=True)
        self.assertEqual(before, (self.app.data / 'db.sqlite3').read_bytes())
        self.assertTrue((self.root / 'pending.json').exists())

    def test_interrupted_namespace_retirement_and_activation_resume_without_manual_repair(self):
        for interrupted_rename in ('retire', 'activate'):
            with self.subTest(point=interrupted_rename):
                self.fail_upgrade()
                real_replace = release.os.replace
                interrupted = []
                def replace(source, destination):
                    real_replace(source, destination)
                    point = 'retire' if Path(source) == self.app.data else 'activate' if Path(destination) == self.app.data else None
                    if point == interrupted_rename and not interrupted:
                        interrupted.append(point)
                        raise SystemExit('injected process death after rename')
                with patch.object(release.os, 'replace', side_effect=replace), self.assertRaises(SystemExit):
                    self.app.recover(strategy='restore', outcome_confirmed=True)
                self.assertTrue(interrupted)
                self.assertTrue((self.root / 'pending.json').exists())
                self.assertFalse(self.live['running'])
                self.app.recover(strategy='restore', outcome_confirmed=True)
                self.assertEqual(release.common.read(self.root / 'current.json')['source'], SOURCE)
                self.assertFalse((self.root / 'pending.json').exists())
                self.assertFalse(any(path.name.startswith('restore-') for path in self.app.data.iterdir()))

    def test_changed_checkpoint_or_missing_containment_blocks_database_restore(self):
        self.fail_upgrade()
        pending = release.common.read(self.root / 'pending.json')
        source = Path(pending['backup']['directory']) / 'verified' / 'db.sqlite3'
        before = (self.app.data / 'db.sqlite3').read_bytes()
        with patch.object(release, 'require_contained', side_effect=release.common.ReleaseError('route')):
            with self.assertRaises(release.common.ReleaseError):
                self.app.recover(strategy='restore', outcome_confirmed=True)
        self.assertEqual(before, (self.app.data / 'db.sqlite3').read_bytes())
        source.write_bytes(b'tampered')
        with self.assertRaisesRegex(release.common.ReleaseError, 'Changed recovery evidence'):
            self.app.recover(strategy='restore', outcome_confirmed=True)

    def test_initial_failure_can_be_contained_and_retained_without_implicit_restore(self):
        with patch.object(self.app, 'ready', side_effect=release.common.ReleaseError('not ready')):
            with self.assertRaises(release.common.ReleaseError):
                self.deploy(initial=True)
        database = (self.app.data / 'db.sqlite3').read_bytes()
        self.app.recover(strategy='restore', outcome_confirmed=True)
        current = release.common.read(self.root / 'current.json')
        self.assertTrue(current['disabled'])
        self.assertFalse(self.live['running'])
        self.assertEqual(database, (self.app.data / 'db.sqlite3').read_bytes())

    def test_real_wal_snapshot_preserves_committed_rows_and_ignores_shm(self):
        connection = sqlite3.connect(self.app.data / 'db.sqlite3')
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute('CREATE TABLE wal_rows(value TEXT)')
        connection.execute("INSERT INTO wal_rows VALUES ('committed-in-wal')")
        connection.commit()
        recovery = self.app.snapshot({'id': uuid.uuid4().hex}, 'wal')
        destination = Path(recovery['directory'])
        self.assertFalse((destination / 'writer-copy' / 'db.sqlite3-shm').exists())
        with closing(sqlite3.connect(destination / 'verified' / 'db.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT value FROM wal_rows').fetchone()[0], 'committed-in-wal')

    def test_hot_rollback_journal_is_replayed_only_in_isolated_copy(self):
        program = """import os,sqlite3,sys
db=sqlite3.connect(sys.argv[1]); db.execute('PRAGMA cache_size=5')
db.execute('CREATE TABLE rows(value TEXT)'); db.execute("INSERT INTO rows VALUES ('original')"); db.commit()
db.execute('BEGIN IMMEDIATE'); db.execute("UPDATE rows SET value='uncommitted'")
db.executemany('INSERT INTO rows VALUES (?)', [('x'*4096,)]*100); os._exit(0)
"""
        subprocess.run([sys.executable, '-c', program, str(self.app.data / 'db.sqlite3')], check=True, timeout=10)
        journal_path = self.app.data / 'db.sqlite3-journal'
        self.assertTrue(journal_path.exists())
        original = {path.name: path.read_bytes() for path in self.app.data.iterdir()}
        recovery = self.app.snapshot({'id': uuid.uuid4().hex}, 'hot-journal')
        self.assertEqual(original, {path.name: path.read_bytes() for path in self.app.data.iterdir()})
        self.assertEqual(original, {path.name: path.read_bytes() for path in
            (Path(recovery['directory']) / 'writer-copy').iterdir()})
        with closing(sqlite3.connect(Path(recovery['directory']) / 'verified' / 'db.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT value FROM rows').fetchall(), [('original',)])

    def test_network_identity_policy_rejects_gateway_drift_and_unknown_members(self):
        network = {'Id': 'original', 'Driver': 'bridge', 'Internal': True, 'EnableIPv6': False,
            'IPAM': {'Config': [{'Subnet': '172.30.92.0/29', 'Gateway': '172.30.92.1', 'IPRange': ''}]},
            'Containers': {'id': {'Name': release.NAME, 'IPv4Address': release.ADDRESS + '/29'}}}
        with patch.object(release.common, 'inspect', return_value=network):
            self.assertEqual(self.real_topology(require_app=True), 'original')
            network['IPAM']['Config'][0]['Gateway'] = '172.30.92.4'
            with self.assertRaises(release.common.ReleaseError):
                self.real_topology()
            network['IPAM']['Config'][0]['Gateway'] = '172.30.92.1'
            network['Containers']['other'] = {'Name': 'unknown', 'IPv4Address': '172.30.92.4/29'}
            with self.assertRaises(release.common.ReleaseError):
                self.real_topology()

    def test_management_records_exact_id_before_start_and_never_retries_timeout(self):
        candidate = self.stage(SOURCE, self.image(SOURCE), {}, 'key')
        directory = Path(candidate['directory'])
        model = {'services': {'authorization': {'image': self.image(SOURCE), 'mem_limit': 192 * 1024**2, 'cpus': '0.5', 'pids_limit': 64,
            'volumes': [{'source': str(self.app.data), 'target': '/data', 'type': 'bind'}], 'environment': {}}}}
        release.common.atomic(directory / 'model.json', model)
        candidate['files'] = release.identity(directory)
        journal = {'id': uuid.uuid4().hex, 'candidate': candidate, 'previous': None, 'tasks': []}
        self.app.journal(journal)
        calls = []
        def docker(*args, **kwargs):
            calls.append(args)
            if args[0] == 'start':
                persisted = release.common.read(self.root / 'pending.json')
                self.assertEqual(persisted['tasks'][0]['id'], 'exact-writer-id')
                raise release.common.CommandTimeout('daemon start outcome unknown')
            return ''
        def start_management(container_id):
            return docker('start', '-a', container_id)
        def inspect(kind, name):
            if kind == 'image':
                return {'Id': 'immutable-image-id'}
            task = journal['tasks'][0]
            return {'Id': 'exact-writer-id', 'Image': 'immutable-image-id', 'Name': '/' + task['name'],
                'State': {'Running': False}, 'Config': {'User': '65532:65532',
                    'Entrypoint': ['/usr/local/bin/python'], 'Cmd': ['/app/manage.py', 'migrate', '--noinput'],
                    'Labels': {release.TASK_LABEL: '1', 'io.jude.mcp-auth.attempt': journal['id']}},
                'HostConfig': {'NetworkMode': 'none', 'Init': True, 'Tmpfs': release.MANAGEMENT_TMPFS, 'LogConfig': {'Type': 'none'}, 'RestartPolicy': {'Name': 'no'}, 'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
                    'SecurityOpt': ['no-new-privileges:true'], 'Memory': 192*1024**2, 'PidsLimit': 64, 'NanoCpus': 500000000},
                'Mounts': [{'Type': 'bind', 'Source': str(self.app.data), 'Destination': '/data', 'RW': True}]}
        with patch.object(release.common, 'docker', side_effect=docker), patch.object(release.common, 'inspect', side_effect=inspect), \
             patch.object(self.app, 'start_management', side_effect=start_management):
            with self.assertRaises(release.common.CommandTimeout):
                release.Release.management(self.app, candidate, journal, 'migrate', '--noinput')
        self.assertEqual([args[0] for args in calls], ['create', 'start'])
        self.assertIn('--network', calls[0])
        self.assertIn('none', calls[0])
        self.assertFalse(release.common.read(self.root / 'pending.json')['tasks'][0]['finished'])
        # Explicit confirmed recovery can resolve a lost create acknowledgement
        # without rerunning create/start, then retire the exact stopped writer.
        recovery_calls = []
        def recovery_docker(*args, **kwargs):
            recovery_calls.append(args)
            return 'exact-writer-id' if args[0] == 'ps' else ''
        with patch.object(release.common, 'docker', side_effect=recovery_docker), \
             patch.object(release.common, 'inspect', side_effect=inspect):
            release.Release.reconcile_tasks(self.app, journal)
            self.assertEqual(journal['tasks'][0]['id'], 'exact-writer-id')
            recovery_calls.clear()
            journal['tasks'][0]['id'] = None
            release.Release.reconcile_tasks(self.app, journal)
            release.Release.cleanup_tasks(self.app, journal)
        self.assertEqual(journal['tasks'][0]['id'], 'exact-writer-id')
        self.assertTrue(journal['tasks'][0]['removed'])
        self.assertEqual([args[0] for args in recovery_calls], ['ps', 'ps', 'rm'])
        self.assertEqual(recovery_calls[-1], ('rm', 'exact-writer-id'))

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink mount aliases')
    def test_symlinked_writable_database_mount_cannot_hide_a_foreign_writer(self):
        alias = self.root / 'data-alias'
        alias.symlink_to(self.app.data, target_is_directory=True)
        item = {'Id': 'foreign', 'State': {'Running': False},
                'Mounts': [{'Type': 'bind', 'RW': True, 'Source': str(alias)}]}
        with patch.object(release.common, 'docker', side_effect=['foreign', json.dumps([item])]), \
             self.assertRaisesRegex(release.common.ReleaseError, 'Untracked'):
            release.Release.writers(self.app, {'tasks': []})

    def test_untracked_writer_sharing_data_or_parent_directory_is_never_adopted(self):
        journal = {'id': uuid.uuid4().hex, 'tasks': []}
        container = {'Id': 'foreign', 'State': {'Running': False},
                     'Mounts': [{'Type': 'bind', 'RW': True, 'Source': str(self.root)}]}
        with patch.object(release.common, 'docker', side_effect=['foreign', json.dumps([container])]), \
             patch.object(release.common, 'inspect', return_value=container), \
             self.assertRaisesRegex(release.common.ReleaseError, 'Untracked'):
            release.Release.writers(self.app, journal)

    def test_management_success_preserves_expected_policy_warnings_privately(self):
        result = release.subprocess.CompletedProcess([], 0, stdout='system check complete',
            stderr='oauth2_provider.W008\nsecurity.W005\nsecurity.W021\n')
        with patch.object(release.subprocess, 'run', return_value=result):
            self.app.start_management('synthetic-writer')
        evidence = [release.common.read(path) for path in (self.root / 'diagnostics').glob('*.json')]
        self.assertEqual(len(evidence), 1)
        self.assertIn('security.W021', evidence[0]['stderr'])
        if os.name != 'nt':
            self.assertEqual(next((self.root / 'diagnostics').iterdir()).stat().st_mode & 0o777, 0o600)


class AuthPolicyTests(unittest.TestCase):
    def test_extra_tmpfs_devices_logs_and_namespace_drift_are_rejected(self):
        expected = {'mem_limit': 192 * 1024**2, 'pids_limit': 64, 'cpus': .25, 'init': True,
                    'tmpfs': ['/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532,mode=0700']}
        host = {'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'],
                'Tmpfs': {'/tmp': expected['tmpfs'][0].split(':', 1)[1]}, 'Init': True,
                'Memory': expected['mem_limit'], 'PidsLimit': 64, 'NanoCpus': 250000000,
                'RestartPolicy': {'Name': 'no'}, 'LogConfig': {'Type': 'none'}}
        release.protected_host(host, expected)
        for key, value in [('Devices', [{'PathOnHost': '/dev/sda'}]), ('LogConfig', {'Type': 'json-file'}),
                           ('PidMode', 'host'), ('Tmpfs', {'/data': 'rw'}), ('CapAdd', ['SYS_ADMIN']),
                           ('Mounts', [{'Type': 'tmpfs', 'Target': '/data'}]), ('RestartPolicy', {'Name': 'always'})]:
            with self.subTest(field=key), patch.dict(host, {key: value}), self.assertRaises(release.common.ReleaseError):
                release.protected_host(host, expected)
        with self.assertRaises(release.common.ReleaseError):
            release.protected_host(host, expected, [{'Type': 'tmpfs', 'Destination': '/data', 'RW': True}])



@unittest.skipIf(os.name == 'nt', 'Linux stable-inode flock and POSIX ownership')
class AuthLockTests(unittest.TestCase):
    def test_shared_maintenance_exclusive_app_and_stable_inode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            for name in ('maintenance.lock', 'mcp-auth.lock'):
                (root / name).touch(mode=0o600)
            before = {path.name: path.stat().st_ino for path in root.iterdir()}
            with release.locks(root):
                with self.assertRaises(release.common.ReleaseError):
                    with release.locks(root):
                        pass
                with self.assertRaises(release.common.ReleaseError):
                    with release.common.maintenance(root / 'maintenance.lock'):
                        pass
            with release.locks(root):
                pass
            self.assertEqual(before, {path.name: path.stat().st_ino for path in root.iterdir()})


if __name__ == '__main__':
    unittest.main()
