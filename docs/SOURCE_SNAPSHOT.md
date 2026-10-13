# Source snapshot

This repository combines the backend and frontend source collected from the
deployed application on **12 October 2026, 23:43 UTC**, with the latest supplied
Android Workday source (`1.2.0-pilot`, version code 4).

The server capture contained 251 source/configuration files: 204 backend and 47
frontend files. Their hashes were verified against the capture manifest before
preparing this public copy. The 42 Alembic revisions form one connected chain
with head `c2b81012a001`.

## Publication adjustments

- Removed a hardcoded development password and password echo from the optional
  bulk-test password utility. A password must now be supplied explicitly.
- Replaced deployment-specific Vite hosts with local development defaults,
  optional explicit host configuration, and API/OpenAPI development proxies.
- Added blank environment templates and an Nginx example required by the
  frontend Dockerfile. The Nginx example expects an API service named `backend`.
- Included the earlier mobile vendor-location table setup SQL and documented
  the existing push-table setup definitions.
- Added portfolio, architecture, configuration and project documentation.

These changes prepare an independent public source copy. They do not update the
running server, alter accounts, change attendance records or send notifications.

## Validation

- All 199 Python source and migration files passed syntax parsing.
- The API imported and generated OpenAPI for 306 paths using isolated placeholder
  configuration, without opening the live database or contacting cloud services.
- `npm ci` and `npm run build` completed from the captured lockfile. The build
  reports a bundle-size warning (the main JavaScript bundle is about 735 kB).
- Android source and existing unit tests are included; an APK was not rebuilt
  during this publication because private Firebase client configuration is excluded.

## Scope

This is a source backup, not an operational disaster-recovery backup. It excludes
environment secrets, Firebase configuration, Android signing keys, databases,
uploaded documents, employee/bank records, location history, logs and private
deployment backups. No live application data or screenshots are included.

The source review checks for credential material and accidental data inclusion;
it is not an independent application security audit. Fresh database installation,
private cloud integrations and physical Android devices require separate
deployment validation.
