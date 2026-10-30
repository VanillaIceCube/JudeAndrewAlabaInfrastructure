// Test-only stdio entrypoint around Oliver's unchanged exported server factory.
// No real credential resolution, network fetch, journal file, or production mode.
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const upstream = process.argv[2];
process.env.YNAB_MCP_NO_AUTOSTART = '1';
process.env.YNAB_DISABLE_AGENT_CONFIG_FALLBACK = '1';
process.env.YNAB_ALLOW_WRITES = '0';
process.env.YNAB_API_TOKEN = 'synthetic-fixture-only';
// Trap any accidental use of the default factory's real fetch, too.
globalThis.fetch = () => { throw new Error('Network access forbidden in fixture'); };
const { createYnabServer } = await import(pathToFileURL(join(upstream, 'index.js')));
const { StdioServerTransport } = await import(pathToFileURL(join(upstream, 'node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js')));
let clock = Date.now();
let writes = 0;
let waiting = 0;
let cancelled = 0;
const payees = [];
const fetchImpl = async (input, init = {}) => {
  const url = new URL(input instanceof Request ? input.url : input);
  assert.equal(url.origin, 'https://api.ynab.com');
  const method = init.method || 'GET';
  let data;
  if (method === 'GET' && url.pathname === '/v1/plans') {
    data = { plans: [{ id: 'fixture-budget', name: 'Synthetic budget' }] };
  } else if (method === 'GET' && url.pathname === '/v1/plans/fixture-budget/payees') {
    data = { payees };
  } else if (method === 'POST' && url.pathname === '/v1/plans/fixture-budget/payees') {
    const payee = { id: `fixture-${++writes}`, ...JSON.parse(init.body).payee };
    payees.push(payee);
    data = { payee };
  } else {
    throw new Error(`Unexpected fake API operation: ${method} ${url.pathname}`);
  }
  return new Response(JSON.stringify({ data }), { headers: { 'content-type': 'application/json' } });
};
const { server } = createYnabServer({
  getAccessToken: async () => 'synthetic-fixture-only', hasCredentials: true,
  defaultBudgetId: 'fixture-budget', fetchImpl, now: () => clock,
  // Explicit test factory option, never YNAB_ALLOW_WRITES=1 or a live token.
  writesEnabled: process.argv[3] === 'synthetic-preview-tests',
});
server.registerTool('fixture_status', { inputSchema: {} }, () => ({
  content: [{ type: 'text', text: JSON.stringify({ pid: process.pid, writes, waiting, cancelled }) }],
}));
server.registerTool('fixture_wait', { inputSchema: {} }, async (_args, extra) => {
  waiting++;
  await new Promise(resolve => {
    const timer = setTimeout(resolve, 10000);
    extra.signal.addEventListener('abort', () => { cancelled++; clearTimeout(timer); resolve(); }, { once: true });
  });
  waiting--;
  return { content: [{ type: 'text', text: 'finished' }] };
});
server.registerTool('fixture_expire', { inputSchema: {} }, () => {
  clock += 300001;
  return { content: [{ type: 'text', text: 'expired' }] };
});
await server.connect(new StdioServerTransport());
