// Deployment policy only; Oliver's application remains unmodified.
import { constants, openSync, fstatSync, readFileSync, closeSync } from 'node:fs';

try {
  if (process.argv.length !== 2) throw new Error('arguments');
  if (process.env.YNAB_ALLOW_WRITES && process.env.YNAB_ALLOW_WRITES !== '0') throw new Error('writes');
  if (process.env.YNAB_API_TOKEN || process.env.YNAB_OP_PATH || process.env.YNAB_MCP_NO_AUTOSTART) throw new Error('credential source');
  if (process.env.YNAB_DISABLE_AGENT_CONFIG_FALLBACK && process.env.YNAB_DISABLE_AGENT_CONFIG_FALLBACK !== '1') throw new Error('fallback');
  const path = process.env.YNAB_API_TOKEN_FILE;
  if (path !== '/run/secrets/ynab_api_token') throw new Error('secret path');
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = fstatSync(fd);
    if (!stat.isFile() || stat.uid !== process.getuid() || (stat.mode & 0o777) !== 0o400 || stat.size < 1 || stat.size > 4096) throw new Error('secret metadata');
    if (!readFileSync(fd, 'utf8').trim()) throw new Error('empty secret');
  } finally { closeSync(fd); }
  process.env.YNAB_ALLOW_WRITES = '0';
  process.env.YNAB_DISABLE_AGENT_CONFIG_FALLBACK = '1';
  delete process.env.SENTRY_DSN;
  await import('/app/index.js');
} catch {
  // Never print paths, exception text, credentials or an upstream stack.
  console.error('YNAB runtime prerequisite failed');
  process.exit(1);
}
