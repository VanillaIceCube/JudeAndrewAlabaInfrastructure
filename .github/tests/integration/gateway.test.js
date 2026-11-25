const assert = require('node:assert/strict');
const { execFileSync, spawnSync } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { setTimeout: delay } = require('node:timers/promises');

const domain = 'notoli.judeandrewalaba.com';
function docker(...args) {
  return execFileSync('docker', args, { encoding: 'utf8', timeout: 120_000 }).trim();
}

test('gateway configuration, recovery state, forwarding and exact proxy trust', async t => {
  const root = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP, 'gateway-check-'));
  const cleanups = [() => fs.rmSync(root, { recursive: true, force: true })];
  t.after(() => {
    const errors = [];
    for (const cleanup of cleanups.reverse()) {
      try { cleanup(); } catch (error) { errors.push(error); }
    }
    if (errors.length) throw new AggregateError(errors, 'Gateway fixture cleanup failed');
  });

  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=ci.invalid',
    '-addext', 'subjectAltName=DNS:' + domain, '-days', '1', '-keyout', path.join(root, 'origin.key'),
    '-out', path.join(root, 'origin.pem')], { stdio: 'pipe' });
  const model = JSON.parse(execFileSync('docker', ['compose', '-f', 'compose.yml', 'config', '--format', 'json'],
    { encoding: 'utf8', env: { ...process.env, INGRESS_CERTS_DIR: root } }));
  const proxy = model.services.proxy;
  function checkConfig(config, ...args) {
    const result = spawnSync('python3', ['nginx/gateway_release.py', 'check-config', '--directory', process.cwd(),
      '--certificates', root, ...args], { input: JSON.stringify(config), encoding: 'utf8', timeout: 240_000 });
    if (result.error) throw result.error;
    assert.equal(result.signal, null);
    return result;
  }

  const validated = checkConfig(model, '--syntax');
  assert.equal(validated.status, 0, validated.stderr);
  const record = JSON.parse(validated.stdout);
  const recordFile = path.join(root, 'record.json');
  fs.writeFileSync(recordFile, JSON.stringify(record));
  assert.equal(checkConfig(model, '--record', recordFile).status, 0);
  fs.writeFileSync(recordFile, JSON.stringify({ ...record, profile: 'unexpected' }));
  assert.equal(checkConfig(model, '--record', recordFile).status, 1);
  const invalid = structuredClone(model);
  invalid.services.proxy.networks.macromapper.ipv4_address = '172.20.0.99';
  assert.equal(checkConfig(invalid).status, 1);

  const configs = fs.readdirSync('nginx/vhosts').filter(file => file.endsWith('.conf'))
    .map(file => fs.readFileSync(path.join('nginx/vhosts', file), 'utf8'));
  for (const app of ['notoli', 'macromapper']) {
    const matches = configs.filter(conf => conf.includes('server_name ' + app + '.judeandrewalaba.com;'));
    assert.equal(matches.length, 1, 'Expected one vhost for ' + app);
    for (const directive of ['set $app_backend ' + app + '-backend:8000;', 'set $app_frontend ' + app + '-frontend:80;',
      'proxy_pass http://$app_backend$request_uri;', 'proxy_pass http://$app_frontend$request_uri;']) {
      assert.ok(matches[0].includes(directive), 'Missing ' + directive);
    }
  }

  const prefix = 'ingress-fixture-' + randomUUID();
  function network(suffix, ...options) {
    const name = prefix + '-' + suffix;
    const id = docker('network', 'create', '--internal', ...options, name);
    cleanups.push(() => docker('network', 'rm', id));
    return name;
  }
  function container(...args) {
    const id = docker('create', ...args);
    cleanups.push(() => docker('rm', '-f', id));
    return id;
  }
  function address(id, networkName) {
    return JSON.parse(docker('container', 'inspect', id))[0].NetworkSettings.Networks[networkName].IPAddress;
  }
  const front = network('front');
  const backend = network('backend', '--subnet', '172.30.88.0/29');
  const observer = path.join(root, 'observer.conf');
  fs.writeFileSync(observer, 'server { listen 80; listen 8000; location / { default_type text/plain; ' +
    'return 200 "$server_port|$remote_addr|$http_x_forwarded_for|$http_x_real_ip|' +
    '$http_x_forwarded_proto|$http_forwarded|$http_x_forwarded_host|$host|$request_uri"; } }');
  function mount(src, dst) { return 'type=bind,src=' + src + ',dst=' + dst + ',readonly'; }
  const mounts = proxy.volumes.flatMap(v => ['--mount', mount(v.source, v.target)]);
  const ingress = container('--network', front, '--network-alias', domain, ...mounts, proxy.image);
  const trustedIp = proxy.networks.notoli_backend.ipv4_address;
  docker('network', 'connect', '--ip', trustedIp, backend, ingress);
  docker('start', ingress);
  for (const [net, alias] of [[front, 'notoli-frontend'], [backend, 'notoli-backend']]) {
    const upstream = container('--network', net, '--network-alias', alias, '--mount',
      mount(observer, '/etc/nginx/conf.d/default.conf'), proxy.image);
    docker('start', upstream);
  }
  const client = container('--network', front, '--entrypoint', 'sleep', '--mount',
    mount(path.join(root, 'origin.pem'), '/etc/ssl/certs/ca-certificates.crt'), proxy.image, '120');
  docker('start', client);
  const clientIp = address(client, front);
  const headers = ['X-Forwarded-For: 198.51.100.17', 'X-Real-IP: 198.51.100.17', 'Forwarded: for=198.51.100.17',
    'X-Forwarded-Host: untrusted.invalid', 'X-Forwarded-Proto: http'].flatMap(header => ['--header', header]);
  for (const [url, port, peer] of [['/', '80', address(ingress, front)],
    ['/api/notifications/?probe=1', '8000', trustedIp], ['/mcp', '8000', trustedIp]]) {
    let response;
    for (let attempt = 1; attempt <= 5; attempt++) {
      try {
        response = execFileSync('docker', ['exec', client, 'wget', '-q', '-O', '-', '-Y', 'off', '-T', '3',
          ...headers, 'https://' + domain + url], { encoding: 'utf8', timeout: 6000 });
        break;
      } catch (error) {
        if (attempt === 5) throw error;
        await delay(1000);
      }
    }
    assert.deepEqual(response.split('|'), [port, peer, clientIp, clientIp, 'https', '', '', domain, url]);
  }
});
