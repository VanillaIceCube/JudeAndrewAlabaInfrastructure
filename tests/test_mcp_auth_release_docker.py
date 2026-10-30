"""Disposable Docker auth writer/recovery fixture; never a production bypass.

Only source staging, scanner and route/companion inventory use synthetic
providers. Compose switching, writer identity, ownership, journal recovery,
management resources, grant invalidation and process/lock failure are real.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_auth_release as release

IMAGE = 'python@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487'
LABEL = 'infrastructure.mcp-auth.release.fixture'
PROGRAM = '''import os,sqlite3,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
os.umask(0o077)
command=sys.argv[1]; version=os.environ['FIXTURE_VERSION']; path='/data/db.sqlite3'
tables=('oauth2_provider_accesstoken','oauth2_provider_refreshtoken','oauth2_provider_grant','django_session')
if command=='migrate' and '--check' not in sys.argv:
 with sqlite3.connect(path) as db:
  db.executescript('CREATE TABLE IF NOT EXISTS version(value TEXT); CREATE TABLE IF NOT EXISTS grants(value TEXT); CREATE TABLE IF NOT EXISTS sessions(value TEXT);')
  db.execute('DELETE FROM version'); db.execute('INSERT INTO version VALUES (?)',(version,))
  db.execute('INSERT INTO grants VALUES (?)',(version,)); db.execute('INSERT INTO sessions VALUES (?)',(version,))
  for table in tables:
   db.execute('CREATE TABLE IF NOT EXISTS '+table+'(value TEXT)'); db.execute('INSERT INTO '+table+' VALUES (?)',(version,))
 if version=='c'*40: raise SystemExit(3)
elif command=='revoke_all_mcp_grants':
 with sqlite3.connect(path) as db:
  db.executescript('DELETE FROM grants; DELETE FROM sessions;')
  for table in tables: db.execute('DELETE FROM '+table)
elif command in ('check','migrate'):
 with sqlite3.connect(path) as db: assert db.execute('SELECT value FROM version').fetchall()==[(version,)]
elif command=='serve':
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args): pass
  def do_GET(self):
   try:
    with sqlite3.connect(path) as db: assert db.execute('SELECT value FROM version').fetchall()==[(version,)]
    self.send_response(200); self.end_headers(); self.wfile.write(b'fixture-ready')
   except Exception: self.send_response(503); self.end_headers()
 HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
else: raise SystemExit(4)
'''


@unittest.skipUnless(os.name != 'nt' and shutil.which('docker'), 'Linux disposable Docker auth fixture')
class AuthDockerReleaseTests(unittest.TestCase):
    def test_canonical_profile_stages_with_private_matched_binds(self):
        with tempfile.TemporaryDirectory(prefix='auth-stage-test-') as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            app = release.Release(root, Path('fixture-scanner'), Path('fixture-cache'))
            app.data.mkdir(mode=0o700)
            os.chown(app.data, 65532, 65532)
            keys = root / 'inputs'
            keys.mkdir(mode=0o700)
            for name in release.KEYS:
                path = keys / name
                path.write_bytes(b'synthetic-canonical-stage-fixture-key')
                os.chown(path, 65532, 65532)
                path.chmod(0o400)
            source = (release.REPO / 'services/mcp-auth/compose.yml').read_text()
            image = 'ghcr.io/vanillaicecube/judeandrewalabainfrastructure-mcp-auth@sha256:' + 'a' * 64
            with patch.object(release, 'source_bytes', return_value=source):
                record = app.stage('a' * 40, image, {name: keys / name for name in release.KEYS}, 'synthetic-key')
            directory = app.directory(record)
            model = release.common.read(directory / 'model.json')
            service = model['services']['authorization']
            self.assertEqual(service['image'], image)
            self.assertEqual(service['profiles'], ['manual-auth'])
            self.assertEqual(len(service['volumes']), 3)
            self.assertEqual(model['networks']['private'], {'external': True, 'name': release.NETWORK})
            self.assertFalse((root / 'pending.json').exists())
            for malformed in (source.replace('profiles: [manual-auth]', 'profiles: [wrong]'),
                              source.replace('    profiles: [manual-auth]\n', '')):
                with patch.object(release, 'source_bytes', return_value=malformed), self.assertRaises(release.common.ReleaseError):
                    app.stage('b' * 40, image, {name: keys / name for name in release.KEYS}, 'synthetic-key')
            self.assertFalse((root / 'pending.json').exists())

    def test_upgrade_failed_migration_restore_and_sigkill_preserve_companions(self):
        prefix = 'auth-release-test-' + uuid.uuid4().hex[:10]
        docker = release.common.docker
        label = LABEL + '=' + prefix
        name, network = prefix + '-server', prefix + '-private'
        octet = int(uuid.uuid4().hex[:2], 16)
        subnet, gateway, address = f'10.248.{octet}.0/29', f'10.248.{octet}.1', f'10.248.{octet}.3'
        with tempfile.TemporaryDirectory(prefix=prefix, dir=os.environ.get('MCP_AUTH_RELEASE_FIXTURE_ROOT')) as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            (root / 'locks').mkdir(mode=0o700)
            for filename in ('maintenance.lock', 'mcp-auth.lock'):
                (root / 'locks' / filename).touch(mode=0o600)
            (root / 'companion.sqlite3').write_bytes(b'synthetic-other-app-db-unchanged')
            (root / 'origin.pem').write_bytes(b'synthetic-certificate-unchanged')
            (root / 'origin.key').write_bytes(b'synthetic-key-unchanged')
            try:
                docker('image', 'inspect', IMAGE)
                docker('network', 'create', '--internal', '--subnet', subnet, '--gateway', gateway, '--label', label, network)
                docker('run', '-d', '--name', prefix + '-companion', '--label', label, '--network', 'none',
                       '--read-only', '--cap-drop', 'ALL', IMAGE, 'python', '-c', 'import time;time.sleep(300)')
                def companions():
                    item = release.common.inspect('container', prefix + '-companion')
                    return {'id': item['Id'], 'started': item['State']['StartedAt'],
                        'files': {filename: hashlib.sha256((root / filename).read_bytes()).hexdigest()
                                  for filename in ('companion.sqlite3', 'origin.pem', 'origin.key')}}
                before = companions()
                def stage(app, source, image, secrets, key_id):
                    directory = root / 'releases' / (source + '-' + uuid.uuid4().hex)
                    directory.mkdir(mode=0o700)
                    program = directory / 'manage.py'
                    program.write_text(PROGRAM)
                    program.chmod(0o444)
                    secret_dir = directory / 'secrets'
                    secret_dir.mkdir(mode=0o700)
                    for filename in release.KEYS:
                        target = secret_dir / filename
                        target.write_bytes(b'synthetic-fixture-only-key')
                        os.chown(target, 65532, 65532)
                        target.chmod(0o400)
                    service = {'image': IMAGE, 'container_name': name, 'user': '65532:65532',
                        'entrypoint': ['/usr/local/bin/python'], 'command': ['/app/manage.py', 'serve'],
                        'environment': {'FIXTURE_VERSION': source, 'PYTHONDONTWRITEBYTECODE': '1'},
                        'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
                        'mem_limit': 192 * 1024**2, 'cpus': '0.5', 'pids_limit': 64, 'restart': 'no',
                        'labels': {LABEL: prefix}, 'logging': {'driver': 'none'},
                        'networks': {'private': {'ipv4_address': address, 'aliases': ['mcp-auth-server']}},
                        'volumes': [{'type': 'bind', 'source': str(app.data), 'target': '/data'},
                            {'type': 'bind', 'source': str(program), 'target': '/app/manage.py', 'read_only': True},
                            *[{'type': 'bind', 'source': str(secret_dir / filename),
                               'target': '/run/secrets/' + filename, 'read_only': True} for filename in release.KEYS]]}
                    release.common.atomic(directory / 'model.json', {'name': prefix,
                        'services': {'authorization': service}, 'networks': {'private': {'name': network, 'external': True}}})
                    release.common.durable_tree(directory)
                    return {'id': directory.name, 'source': source, 'directory': str(directory), 'image': IMAGE,
                            'key_id': key_id, 'files': release.identity(directory)}
                with patch.object(release, 'PROJECT', prefix), patch.object(release, 'NAME', name), \
                     patch.object(release, 'NETWORK', network), patch.object(release, 'SUBNET', subnet), \
                     patch.object(release, 'GATEWAY', gateway), patch.object(release, 'ADDRESS', address), \
                     patch.object(release, 'IMAGE', re.compile(re.escape(IMAGE))), \
                     patch.object(release, 'baseline', side_effect=companions), \
                     patch.object(release, 'require_contained', return_value=None), \
                     patch.object(release, 'preflight', return_value={'fixture-only': True}) as scanner, \
                     patch.object(release.Release, 'stage', autospec=True, side_effect=stage):
                    app = release.Release(root, Path('fixture-scanner'), Path('fixture-cache'))
                    app.data.mkdir(mode=0o700)
                    os.chown(app.data, 65532, 65532)
                    network_id = release.topology()
                    with release.locks(root / 'locks'):
                        app.deploy('a' * 40, IMAGE, {}, 'synthetic-key', initial=True)
                        first = release.common.read(root / 'current.json')
                        app.deploy('b' * 40, IMAGE, {}, 'synthetic-key')
                        app.rollback(strategy='restore', outcome_confirmed=True)
                    restored = release.common.read(root / 'current.json')
                    self.assertEqual(restored['source'], 'a' * 40)
                    self.assertEqual(restored['files'], first['files'])
                    with closing(sqlite3.connect(app.data / 'db.sqlite3')) as db:
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM grants').fetchone()[0], 0)
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
                    with release.locks(root / 'locks'):
                        with self.assertRaises(release.common.ReleaseError):
                            app.deploy('c' * 40, IMAGE, {}, 'synthetic-key')
                        self.assertTrue((root / 'pending.json').exists())
                        with self.assertRaises(release.common.ReleaseError):
                            app.recover(strategy='keep', outcome_confirmed=True)
                        app.recover(strategy='restore', outcome_confirmed=True)
                    child = os.fork()
                    if child == 0:
                        try:
                            with release.locks(root / 'locks'), patch.object(release.Release, 'ready',
                                    side_effect=lambda: os.kill(os.getpid(), signal.SIGKILL)):
                                app.deploy('d' * 40, IMAGE, {}, 'synthetic-key')
                        finally:
                            os._exit(2)
                    _, status = os.waitpid(child, 0)
                    self.assertTrue(os.WIFSIGNALED(status))
                    self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
                    reopened = release.Release(root, Path('fixture-scanner'), Path('fixture-cache'))
                    with release.locks(root / 'locks'):
                        with self.assertRaises(release.common.ReleaseError):
                            reopened.deploy('b' * 40, IMAGE, {}, 'synthetic-key')
                        reopened.recover(strategy='restore', outcome_confirmed=True)
                    accepted = release.common.read(root / 'current.json')
                    self.assertEqual(accepted['source'], 'a' * 40)
                    self.assertEqual(accepted['files'], first['files'])
                    self.assertEqual(release.topology(require_app=True), network_id)
                    self.assertEqual(companions(), before)
                    self.assertFalse((root / 'pending.json').exists())
                    self.assertGreaterEqual(scanner.call_count, 9)
            finally:
                # Exact fixture labels and privately recorded management names;
                # never prune unrelated containers, networks, images or volumes.
                for path in [root / 'pending.json', *(root / 'attempts').glob('*.json')]:
                    if path.exists():
                        for task in json.loads(path.read_text()).get('tasks', []):
                            ids = docker('ps', '-aq', '--filter', 'name=^/' + task['name'] + '$').split()
                            if ids:
                                docker('container', 'rm', '-f', *ids)
                for kind in ('container', 'network'):
                    ids = docker(kind, 'ls', '-aq' if kind == 'container' else '-q', '--filter', 'label=' + label).split()
                    if ids:
                        docker(kind, 'rm', *(['-f', '-v'] if kind == 'container' else []), *ids)


if __name__ == '__main__':
    unittest.main(verbosity=2)
