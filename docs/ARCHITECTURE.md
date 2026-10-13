# Architecture notes

## Clients and API

The React application presents organisation operations as modules. A shared request layer supplies the access token and handles refresh. The Android app combines a native Workday interface with the HTTPS workspace in a restricted WebView.

The FastAPI backend validates input with Pydantic and persists records through SQLAlchemy. PostgreSQL is the primary database. Redis and background services support asynchronous work. Alembic records schema changes; some mobile additions also have explicit schema setup, which must be included when validating a clean installation.

## Identity and organisation scope

An organisation code identifies the organisation at login. Authenticated users have roles such as Admin, MD, GM, manager and employee. Features apply their permission checks and organisation scope in the backend, in addition to showing appropriate controls in the clients.

This is a shared application with organisation-scoped data. It does not claim to provision a separate physical database for every organisation.

## Work-session location

The Android foreground service starts from a user-visible workday flow and keeps a persistent tracking notification. The controller checks the server's attendance state, queues samples when delivery is interrupted, and validates the session before continuing collection. Checkout stops collection.

The app does not bypass Android permissions or operating-system force-stop controls. Its session lease and maximum work-session duration bound tracking if server verification is lost. Tracking is best effort; its sample interval is not a real-time guarantee.

## Alerts

Workflow events create in-app notifications. The Android push worker queues eligible notifications for registered accounts and sends them through Firebase Cloud Messaging. Opening an alert navigates to the relevant work item. Notification permission, Google Play services, network and device restrictions influence delivery.

## Financial workflows

Payroll and expense modules record amounts and apply management approval rules. Box Loading follows a draft, MD review, approval/rejection and disbursement-recording flow. Its server recalculates totals, locks financial input after submission, uses row locks and version checks for state transitions, and stores action snapshots.

## Operations

The deployed system uses a Lightsail Ubuntu host with Caddy providing HTTPS. PostgreSQL and Redis run as supporting services, and systemd manages the API, web service and push worker. Deployment credentials, database contents and uploaded documents are separate from the public source repository.
