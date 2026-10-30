import { test } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

const gateway = process.env.POC_GATEWAY_SOURCE;
const upstream = process.env.POC_YNAB_SOURCE;
const { stdioToStatefulStreamableHttpMount } = await import(pathToFileURL(join(gateway, 'dist/gateways/stdioToStatefulStreamableHttp.js')));
const child = fileURLToPath(new URL('./fake-child.mjs', import.meta.url));
const headers = { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25', connection: 'close' };
let nextId = 1;
const logger = { info() {}, error() {}, debug() {} };

async function start(t, { preview = false, timeout = 600000 } = {}) {
  const key = randomBytes(32).toString('hex');
  const mount = stdioToStatefulStreamableHttpMount({
    stdioCmd: { command: process.execPath, args: [child, upstream, preview ? 'synthetic-preview-tests' : 'read-only'] },
    streamableHttpPath: '/mcp', logger, corsOrigin: false, healthEndpoints: [],
    headers: { 'Cache-Control': 'no-store' }, apiKeys: [key], sessionTimeout: timeout,
  });
  const listener = mount.app.listen(0, '127.0.0.1');
  await once(listener, 'listening');
  t.after(async () => {
    await mount.close();
    listener.closeAllConnections();
    await new Promise(resolve => listener.close(resolve));
  });
  const url = `http://127.0.0.1:${listener.address().port}/mcp`;
  async function request(method, params = {}, session, options = {}) {
    const response = await fetch(url, {
      method: 'POST', headers: { ...headers, authorization: `Bearer ${key}`, ...(session ? { 'mcp-session-id': session } : {}), ...options.headers },
      body: options.body ?? JSON.stringify({ jsonrpc: '2.0', id: nextId++, method, params }),
      signal: AbortSignal.timeout(15000),
    });
    const text = await response.text();
    const data = text.startsWith('event:') || text.startsWith('id:')
      ? JSON.parse(text.split('\n').find(line => line.startsWith('data:')).slice(5))
      : text ? JSON.parse(text) : null;
    return { response, data };
  }
  async function initialize() {
    const result = await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'fixture', version: '1' } });
    assert.equal(result.response.status, 200);
    assert.ok(result.data.result.capabilities.tools);
    const session = result.response.headers.get('mcp-session-id');
    assert.ok(session);
    const ready = await request('notifications/initialized', {}, session, { body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) });
    assert.equal(ready.response.status, 202);
    return session;
  }
  async function call(session, name, args = {}) {
    const result = await request('tools/call', { name, arguments: args }, session);
    assert.equal(result.response.status, 200);
    return result.data.result;
  }
  async function end(session) {
    return fetch(url, { method: 'DELETE', headers: { ...headers, authorization: `Bearer ${key}`, 'mcp-session-id': session }, signal: AbortSignal.timeout(5000) });
  }
  return { key, url, request, initialize, call, end };
}

const value = result => result.structuredContent?.result ?? JSON.parse(result.content[0].text);
const failure = result => { assert.equal(result.isError, true); return result.content[0].text; };
const input = { budgetId: 'fixture-budget', name: 'Synthetic payee' };
const preview = async (g, s) => value(await g.call(s, 'preview_write_tool', { tool_name: 'create_payee', input })).preview_token;
const execute = (g, s, token, args = {}) => g.call(s, 'create_payee', { ...input, previewToken: token, confirmed: true, ...args });

test('authentication precedes parsing and session access on every HTTP method', async t => {
  const g = await start(t);
  for (const method of ['POST', 'GET', 'DELETE']) {
    for (const authorization of ['', 'Bearer wrong-key']) {
      const response = await fetch(g.url, { method, headers: { ...headers, authorization, 'x-forwarded-user': 'owner', 'x-forwarded-for': '127.0.0.1' }, ...(method === 'POST' ? { body: '{broken' } : {}) });
      assert.equal(response.status, 401);
      assert.equal(response.headers.get('www-authenticate'), 'Bearer realm="supergateway"');
      assert.equal(response.headers.get('cache-control'), 'no-store');
      await response.text();
    }
  }
  assert.equal((await g.request('tools/list', {}, undefined, { body: '{broken' })).response.status, 400);
  assert.equal((await g.request('tools/list', {}, 'unknown-session')).response.status, 404);
});

test('read-only discovery/calls and stable child across new TCP requests and SSE reconnect', async t => {
  const g = await start(t);
  const session = await g.initialize();
  const tools = (await g.request('tools/list', {}, session)).data.result.tools;
  assert.ok(tools.some(tool => tool.name === 'list_budgets'));
  assert.ok(!tools.some(tool => tool.name === 'create_payee'));
  const first = value(await g.call(session, 'fixture_status'));
  assert.equal(value(await g.call(session, 'list_budgets')).budgets[0].id, 'fixture-budget');
  assert.match(failure(await execute(g, session, 'invented')), /not found|Unknown|disabled/i);
  const controller = new AbortController();
  const stream = await fetch(g.url, { headers: { ...headers, authorization: `Bearer ${g.key}`, 'mcp-session-id': session }, signal: controller.signal });
  assert.equal(stream.status, 200);
  controller.abort();
  assert.deepEqual(value(await g.call(session, 'fixture_status')), first);
  assert.equal(first.writes, 0);
  // Express accepts a trailing slash internally; the future public edge must
  // enforce exact /mcp instead of assuming the upstream does so.
  const alias = await fetch(`${g.url}/`, {
    method: 'POST', headers: { ...headers, authorization: `Bearer ${g.key}`, 'mcp-session-id': session },
    body: JSON.stringify({ jsonrpc: '2.0', id: nextId++, method: 'tools/list' }),
  });
  assert.equal(alias.status, 200);
  await alias.text();
  const metadata = await fetch(new URL('/.well-known/oauth-protected-resource/mcp', g.url), { headers: { authorization: `Bearer ${g.key}` } });
  assert.equal(metadata.status, 404);
  await metadata.text();
  const other = await g.initialize();
  assert.notEqual(value(await g.call(other, 'fixture_status')).pid, first.pid);
  await g.end(session);
  assert.equal((await g.request('tools/list', {}, session)).response.status, 404);
});

test('upstream preview requires separate confirmation and is single-use in the same HTTP session', async t => {
  const g = await start(t, { preview: true });
  const session = await g.initialize();
  const token = await preview(g, session);
  assert.ok(token);
  assert.equal(value(await g.call(session, 'fixture_status')).writes, 0);
  assert.match(failure(await execute(g, session, token, { confirmed: false })), /confirm|literal|true/i);
  const raced = await Promise.all([execute(g, session, token), execute(g, session, token)]);
  assert.equal(raced.filter(result => !result.isError).length, 1);
  assert.equal(raced.filter(result => result.isError).length, 1);
  assert.match(failure(await execute(g, session, token)), /already used|missing|expired/i);
  assert.equal(value(await g.call(session, 'fixture_status')).writes, 1);
});

test('preview cannot move sessions or change the approved payload; stale tokens are consumed', async t => {
  const g = await start(t, { preview: true });
  const a = await g.initialize();
  const b = await g.initialize();
  const token = await preview(g, a);
  assert.match(failure(await execute(g, b, token)), /session|missing/i);
  assert.match(failure(await execute(g, a, token, { name: 'Altered' })), /Stale preview/i);
  assert.match(failure(await execute(g, a, token)), /already used|missing/i);
  assert.equal(value(await g.call(a, 'fixture_status')).writes, 0);
  assert.equal(value(await g.call(b, 'fixture_status')).writes, 0);
});

test('five-minute expiry and child replacement invalidate previews without writes', async t => {
  const g = await start(t, { preview: true });
  const a = await g.initialize();
  const expired = await preview(g, a);
  await g.call(a, 'fixture_expire');
  assert.match(failure(await execute(g, a, expired)), /expired/i);
  const token = await preview(g, a);
  await g.end(a);
  const b = await g.initialize();
  assert.match(failure(await execute(g, b, token)), /missing|session/i);
  assert.equal(value(await g.call(b, 'fixture_status')).writes, 0);
});

test('different principals require separate instances; session IDs do not cross instances', async t => {
  const a = await start(t);
  const b = await start(t);
  const session = await a.initialize();
  assert.equal((await b.request('tools/list', {}, session)).response.status, 404);
  assert.equal((await a.request('tools/list', {}, session, { headers: { authorization: `Bearer ${b.key}` } })).response.status, 401);
});

test('concurrent calls and cancellation preserve the session; idle timeout invalidates it', async t => {
  const g = await start(t, { timeout: 500 });
  const s = await g.initialize();
  const controller = new AbortController();
  const pending = fetch(g.url, {
    method: 'POST', headers: { ...headers, authorization: `Bearer ${g.key}`, 'mcp-session-id': s },
    body: JSON.stringify({ jsonrpc: '2.0', id: 'cancel-fixture', method: 'tools/call', params: { name: 'fixture_wait', arguments: {} } }),
    signal: controller.signal,
  }).then(r => r.text()).catch(() => {});
  const first = value(await g.call(s, 'fixture_status'));
  let state = first;
  for (let attempt = 0; state.waiting !== 1 && attempt < 20; attempt++) {
    await delay(25);
    state = value(await g.call(s, 'fixture_status'));
  }
  assert.equal(state.waiting, 1);
  const cancel = await g.request('notifications/cancelled', {}, s, {
    body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/cancelled', params: { requestId: 'cancel-fixture', reason: 'fixture cancellation' } }),
  });
  assert.equal(cancel.response.status, 202);
  controller.abort();
  await pending;
  for (let attempt = 0; state.cancelled !== 1 && attempt < 20; attempt++) {
    await delay(25);
    state = value(await g.call(s, 'fixture_status'));
  }
  assert.equal(state.cancelled, 1);
  assert.equal(state.pid, first.pid);
  await delay(750);
  assert.equal((await g.request('tools/list', {}, s)).response.status, 404);
});
