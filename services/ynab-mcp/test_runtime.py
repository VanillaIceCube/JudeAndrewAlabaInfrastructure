"""Disposable daemon acceptance for #58. Only synthetic secrets; zero API access."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ynab_build', HERE / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
preflight_spec = importlib.util.spec_from_file_location('ynab_validate', HERE / 'validate.py')
preflight = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(preflight)
RUN_ID = os.environ.get('YNAB_RUNTIME_TEST_ID', 'ynab-runtime-test-' + uuid.uuid4().hex)
LABEL = 'infrastructure.ynab.fixture'


def docker(*args, check=True, input=None):
    if args[0] == 'run':
        args = ('run', '--label', LABEL + '=' + RUN_ID, *args[1:])
    return subprocess.run(['docker', *args], input=input, text=True, capture_output=True,
                          check=check, timeout=180)


def cleanup(identity):
    import re
    if not re.fullmatch(r'ynab-runtime-test-[a-f0-9]{32}', identity):
        raise ValueError('Invalid fixture identity')
    containers = docker('ps', '-aq', '--filter', 'label=' + LABEL + '=' + identity).stdout.split()
    if containers:
        docker('rm', '-f', *containers, check=False)
    docker('volume', 'rm', identity + '-secret', check=False)
    docker('image', 'rm', identity + ':fixture', check=False)


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = RUN_ID
        import re
        if not re.fullmatch(r'ynab-runtime-test-[a-f0-9]{32}', cls.identity):
            raise ValueError('Invalid fixture identity')
        cls.image = cls.identity + ':fixture'
        cls.volume = cls.identity + '-secret'
        cls.temp = tempfile.TemporaryDirectory(prefix='ynab-runtime-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.addClassCleanup(lambda: docker('image', 'rm', cls.image, check=False))
        builder.build(cls.image, Path(cls.temp.name) / 'record.json')
        docker('volume', 'create', cls.volume)
        cls.addClassCleanup(lambda: docker('volume', 'rm', cls.volume, check=False))
        # The volume contains a fixed synthetic token only; no host secret mount.
        docker('run', '--rm', '--network', 'none', '--user', '0', '--entrypoint', 'node',
               '--volume', cls.volume + ':/fixture', builder.PIN['build_image'], '-e',
               "const f=require('node:fs'); f.writeFileSync('/fixture/ynab_api_token','synthetic-fixture-only'); f.chmodSync('/fixture/ynab_api_token',0o400); f.chownSync('/fixture/ynab_api_token',65532,65532)")

    def run_runtime(self, extra=(), protocol=False, secret=True):
        args = ['run', '--rm', '--read-only', '--network', 'none', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--pids-limit', '32', '--memory', '256m',
                '--cpus', '0.5', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532,mode=0700']
        if secret:
            args += ['--mount', f'type=volume,source={self.volume},target=/run/secrets,readonly',
                     '-e', 'YNAB_API_TOKEN_FILE=/run/secrets/ynab_api_token']
        args += list(extra) + ['-i', self.image]
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-11-25', 'capabilities': {},
                'clientInfo': {'name': 'runtime-fixture', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
             'params': {'name': 'ynab_auth_status', 'arguments': {}}},
        ]
        return docker(*args, check=False, input=''.join(json.dumps(m) + '\n' for m in messages) if protocol else '')

    def test_actual_upstream_stdio_is_read_only_without_network_or_writable_root(self):
        result = self.run_runtime(protocol=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = {m['id']: m for line in result.stdout.splitlines() if (m := json.loads(line)).get('id')}
        self.assertIn('result', replies[1])
        names = {tool['name'] for tool in replies[2]['result']['tools']}
        self.assertIn('list_budgets', names)
        self.assertFalse(names & {'create_transaction', 'update_transaction', 'delete_transaction', 'create_payee', 'ynab_write_tool_execute'})
        auth = replies[3]['result']
        status = auth.get('structuredContent', {}).get('result') or json.loads(auth['content'][0]['text'])
        self.assertTrue(status['authenticated'])
        self.assertFalse(status['writes_enabled'])
        self.assertEqual(status['credential_source'], 'token_file')
        self.assertEqual(result.stderr, '')

    def test_missing_secret_and_unsafe_overrides_fail_without_leaking_values(self):
        for extra, secret in [((), False), (('-e', 'YNAB_ALLOW_WRITES=1'), True),
                              (('-e', 'YNAB_DISABLE_AGENT_CONFIG_FALLBACK=0'), True),
                              (('-e', 'YNAB_API_TOKEN=synthetic-do-not-print'), True)]:
            with self.subTest(extra=extra):
                result = self.run_runtime(extra, secret=secret)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.strip(), 'YNAB runtime prerequisite failed')
                self.assertNotIn('synthetic', result.stdout + result.stderr)

    def test_image_is_nonroot_and_compose_has_no_shared_networks_or_ports(self):
        image = json.loads(docker('image', 'inspect', self.image).stdout)[0]
        self.assertEqual(image['Config']['User'], '65532:65532')
        self.assertEqual(image['Config']['Labels']['org.opencontainers.image.revision'], builder.PIN['commit'])
        env = dict(os.environ, YNAB_RUNTIME_REPOSITORY='ghcr.io/fixture/ynab', YNAB_RUNTIME_SHA256='a' * 64,
                   YNAB_TOKEN_FILE=str(Path(self.temp.name) / 'synthetic-token'))
        config = subprocess.check_output(['docker', 'compose', '-f', str(HERE / 'compose.yml'),
                                          '--profile', 'manual-stdio', 'config', '--format', 'json'], env=env, text=True)
        service = json.loads(config)['services']['runtime']
        self.assertEqual(service['image'], 'ghcr.io/fixture/ynab@sha256:' + 'a' * 64)
        self.assertEqual(service['network_mode'], 'none')
        self.assertTrue(service['read_only'])
        self.assertFalse(service.get('ports'))
        self.assertFalse(service.get('networks'))
        self.assertFalse(service.get('volumes'))
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertEqual(service['logging']['driver'], 'none')

    def test_recipe_cannot_hide_a_changed_base_or_unvalidated_copy_in_comments(self):
        recipe = (HERE / 'Dockerfile').read_text(encoding='utf-8')
        for altered in [
            recipe.replace('FROM ' + builder.PIN['runtime_image'], 'FROM node:latest') + '\n# ' + builder.PIN['runtime_image'],
            recipe + '\ncopy\tprivate-secret /app/private-secret\n',
            recipe + '\nENV YNAB_ALLOW_WRITES=1\n',
        ]:
            with self.subTest(altered=altered[-80:]):
                with self.assertRaises(ValueError):
                    builder.validate_recipe(altered)

    def test_preflight_rejects_invalid_digest_before_reading_any_secret(self):
        for image in ['ghcr.io/fixture/ynab:latest', 'ghcr.io/fixture/ynab@sha256:latest',
                      'ghcr.io/fixture/ynab@sha256:' + 'A' * 64]:
            with self.subTest(image=image):
                with self.assertRaisesRegex(ValueError, 'reviewed registry image'):
                    preflight.validate(image, Path(self.temp.name) / 'does-not-exist')

    def test_invalid_secret_metadata_and_empty_content_fail_closed(self):
        for mutation in ["f.chmodSync(p,0o644)", "f.writeFileSync(p,'')", "f.chownSync(p,0,0)"]:
            with self.subTest(mutation=mutation):
                docker('run', '--rm', '--network', 'none', '--user', '0', '--entrypoint', 'node',
                       '--volume', self.volume + ':/fixture', builder.PIN['build_image'], '-e',
                       "const f=require('node:fs'),p='/fixture/ynab_api_token';" + mutation)
                try:
                    result = self.run_runtime()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stderr.strip(), 'YNAB runtime prerequisite failed')
                finally:
                    docker('run', '--rm', '--network', 'none', '--user', '0', '--entrypoint', 'node',
                           '--volume', self.volume + ':/fixture', builder.PIN['build_image'], '-e',
                           "const f=require('node:fs'),p='/fixture/ynab_api_token';f.chmodSync(p,0o600);f.writeFileSync(p,'synthetic-fixture-only');f.chmodSync(p,0o400);f.chownSync(p,65532,65532)")


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--cleanup':
        cleanup(sys.argv[2])
    else:
        try:
            unittest.main(verbosity=2)
        finally:
            cleanup(RUN_ID)
