# 🧰 Manual recovery tools

This folder retains the manual SQLite snapshot helper for the one-time ingress
cutover. CI helpers belong in `.github/tools/`, gateway operations in `nginx/`,
and release-manifest maintenance in `app-release/`.

## 🧭 Structure

- [snapshot_sqlite.py](snapshot_sqlite.py): capture SQLite from an application
  container and verify an isolated restore in a new private recovery directory.

## 🚀 Operations

Follow the [cutover and reversal procedure](../docs/cutover.md) within its
separately authorized hold. The helper preserves the source database; off-host
protection remains an operator step. It is not a recurring backup service.

## 🧪 Checks

The root snapshot regression suite has been retired. This manual helper is not
exercised by current CI; follow the authorized recovery procedure and never run
a production cutover as a test.
