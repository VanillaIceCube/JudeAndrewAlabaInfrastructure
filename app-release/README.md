# Shared application launcher

[`v1/release.py`](v1/release.py) launches the backend and frontend for FullStackTemplate, Notoli, and MacroMapper. Each app owns its reviewed Compose file, environment and readiness rules. Infrastructure owns this launcher, the bundle builder, the common tests, and the generated deployment workflow.

## Launch

1. The app workflow verifies the pinned source, builds the two images and uploads a checksummed bundle to `$DEPLOY_PATH/incoming/$RELEASE_ID`. Only the deploying identity may read the environment file. The release ID identifies the source commit and GitHub run attempt.
2. The launcher acquires a shared host maintenance lock and the app’s exclusive deployment lock. It checks the bundle, existing database, trusted gateway and external route networks before pulling the exact image digests.
3. It stops this app’s backend writers and uses the new backend image on the app’s egress network to run `manage.py check --deploy` and `migrate --noinput`.
4. It runs `docker compose up -d` for the two services, checks their actual port bindings and networks, then probes the direct backend and public routes. A failed check exits nonzero.

Applications bind one SQLite file. A stopped writer may still hold its WAL or rollback journal in the container. The launcher refuses to replace that writer or discard an interrupted migration with a journal. Preserve it and have the operator checkpoint the database. Deployments do not capture databases, select historical controllers or restore an older release. Deployment files and any existing host data remain private.

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
