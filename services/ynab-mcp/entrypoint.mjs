// Deployment policy only; Oliver's application remains unmodified.
import { constants, openSync, fstatSync, lstatSync, readFileSync, closeSync } from 'node:fs';

try {
  if (process.argv.length !== 2) throw new Error('arguments');
  const writes = process.env.YNAB_ALLOW_WRITES ?? '0';
  if (!['0', '1'].includes(writes)) throw new Error('writes');
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
  if (writes === '1' || process.env.HOME === '/data') {
    if (process.env.HOME !== '/data') throw new Error('persistent journal required');
    const data = lstatSync('/data');
    if (!data.isDirectory() || data.uid !== process.getuid() || data.gid !== process.getgid() || (data.mode & 0o777) !== 0o700) throw new Error('journal directory');
    try {
      const journal = '/data/.ynab-mcp-undo.json';
      const jfd = openSync(journal, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
      try {
        const info = fstatSync(jfd);
        if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o777) !== 0o600) throw new Error('journal metadata');
        if (!Array.isArray(JSON.parse(readFileSync(jfd, 'utf8')))) throw new Error('journal data');
      } finally { closeSync(jfd); }
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  process.umask(0o077);
  process.env.YNAB_ALLOW_WRITES = writes;
  process.env.YNAB_DISABLE_AGENT_CONFIG_FALLBACK = '1';
  delete process.env.SENTRY_DSN;
  await import('/app/index.js');
} catch {
  // Never print paths, exception text, credentials or an upstream stack.
  console.error('YNAB runtime prerequisite failed');
  process.exit(1);
}
