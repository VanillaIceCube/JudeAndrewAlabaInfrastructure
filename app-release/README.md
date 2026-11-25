# Shared application launcher

[`v1/release.py`](v1/release.py) launches the backend and frontend for FullStackTemplate, Notoli, and MacroMapper. Each app owns its reviewed Compose file, environment and readiness rules. Infrastructure owns this launcher, the bundle builder, the common tests, and the generated deployment workflow.

## Launch

1. The app workflow verifies the pinned source, builds the two images and uploads a checksummed bundle to `$DEPLOY_PATH/incoming/$RELEASE_ID`. Only the deploying identity may read the environment file. The release ID identifies the source commit and GitHub run attempt.
2. The launcher acquires a shared host maintenance lock and the app’s exclusive deployment lock. It checks the bundle, existing database, trusted gateway and external route networks before pulling the exact image digests.
3. It stops this app's existing frontend and backend, checks the SQLite journals, and saves the database and containers together. Migration starts only after the complete backup is in place.
4. The new backend image runs `manage.py check --deploy` and `migrate --noinput`. Compose then starts both services and the launcher checks their port bindings, networks, direct backend response and public routes.
5. If startup or post-start host validation fails, or either health check still fails after retries, the launcher stops both services and fails the deployment. A public-route failure also takes this app offline. The shared gateway and other apps keep serving. The next launch requires a new attempt. The production services use `restart: unless-stopped` so a daemon restart respects that stop.

## Pre-migration backup

Each deployment attempt keeps its own private `$DEPLOY_PATH/incoming/$RELEASE_ID/before-migration/` on the host. A retry leaves earlier copies available. On first launch the directory contains the existing database and an empty container inventory.

| File | Contents |
| --- | --- |
| `db.sqlite3` | A snapshot made with the SQLite backup API after writers stop. The launcher checks its integrity before migrating. |
| `backend.tar` and `frontend.tar` | A loadable Docker image for each existing app container, including its writable filesystem and configuration. |
| `containers.json` | The corresponding Docker inspect records from before shutdown, including the original image IDs, mounts, environment and network settings. |

Applications bind one SQLite file. A stopped writer can still hold committed data in a container-local WAL or rollback journal. If the launcher reports a journal, preserve that container and have the operator checkpoint it before retrying. Unexpected data mounts also block the backup because Docker excludes mounts from container snapshots.

Keep these files private. Both the archives and the inventory can contain application credentials. Allow disk space for the database and both containers for each retained attempt. Include these directories in the host's backup retention policy and keep the last working set while a failed release is investigated.

For a manual recovery rehearsal, copy the database into a private test directory and use `docker image load --input backend.tar` and `docker image load --input frontend.tar` for the available archives. Their local tags are `<app>-backup-backend:<attempt>` and `<app>-backup-frontend:<attempt>`. Use the saved runtime settings with isolated networks and the copied database. A production restore is a separate operator action. Preserve the failed database and journals and account for writes accepted since the snapshot before replacing live data. The app can receive traffic while readiness runs.

## Host inputs

The deployment identity owns the app root and its `incoming/` directory (0700) and can access the existing nonempty `db.sqlite3`. The host operator provisions the external networks, gateway, and `/var/lib/jude-deploy-locks` with a stable `maintenance.lock` and `<app>.lock` (0600). The gateway holds the maintenance lock exclusively during its own launch.

`app.json` declares each app’s service and container names, network membership, exact trusted peers, database bind, production environment values, and readiness responses. An offline companion application may be absent. An unexpected peer, subnet or published backend port fails the checks. Each app documents its SSH access variables, secrets and optional MCP settings in its production guide.

## Update the source and its consumers

1. Change [the launcher](v1/release.py), [bundle builder](v1/build_bundle.py), [workflow template](v1/workflow.yml), or [tests](v1/tests/) here. Regenerate and check the manifest.

   ```sh
   python3 app-release/update_release_manifest.py
   python3 app-release/update_release_manifest.py --check
   ```

2. Commit the canonical files and set `deploy/production/app.json` → `shared_source.commit` in each app to that full SHA. When the set of shared files changes, use the new builder in each consumer. Run from the application root.

   ```sh
   python3 deploy/production/build_bundle.py --check-parity --source-root ../JudeAndrewAlabaInfrastructure --sync
   python3 -m unittest discover -s deploy/tests -v
   ```

3. Publish the canonical commit before remote consumer checks. `--check-parity` without `--source-root` checks the immutable GitHub revision. The pinned template fixture in Infrastructure CI exercises the candidate launcher against real consumer configuration.

FullStackTemplate provides onboarding examples. Each live app controls its own promotion, credentials and production acceptance. Gateway operations are described in the [Nginx guide](../nginx/README.md).
