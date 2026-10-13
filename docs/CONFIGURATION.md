# Configuration and local setup

Use a separate development database and your own credentials. The source snapshot and publication adjustments are recorded in [SOURCE_SNAPSHOT.md](SOURCE_SNAPSHOT.md).

## Backend

Copy `backend/.env.example` to `backend/.env` outside version control and fill the blank values. Settings used by the application include:

| Setting | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection using the psycopg driver |
| `REDIS_URL` | Redis connection |
| `JWT_SECRET_KEY` | A new randomly generated signing secret |
| `INITIAL_ORGANIZATION_NAME` / `INITIAL_ORGANIZATION_CODE` | Development organisation for initial setup |
| `INITIAL_ADMIN_EMPLOYEE_CODE` / `INITIAL_ADMIN_PASSWORD` | Initial development administrator |
| `AWS_REGION` / `S3_DOCUMENT_BUCKET` | Your document-storage configuration |
| `PUBLIC_FRONTEND_URL` | Your frontend origin used in inspection/vendor links |
| `FIREBASE_CREDENTIALS_FILE` / `FIREBASE_PROJECT_ID` | Private push-worker service account path and expected project |

Generate a JWT secret locally with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Use different credentials for development and deployment. Never commit the resulting values.

Create a virtual environment under `backend` and install `requirements.txt`:

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# On Windows PowerShell, use .\.venv\Scripts\Activate.ps1 instead.
python -m pip install -r requirements.txt
python -m alembic heads
```

After configuring and checking the **empty development database**, apply `python -m alembic upgrade head`. The recorded head is `c2b81012a001`. The initial-data script is `python -m app.scripts.seed_initial_data`; it uses the initial-account environment settings. Initial user creation and employee attendance-profile setup are separate operations: ensure an administrator who will check in has an employee profile too.

Mobile tracking and push were added incrementally. Follow [mobile schema setup](../backend/scripts/README.md) for their additional tables. A source snapshot and a connected revision graph do not establish that a fresh-database installation has passed.

Start the API from `backend` with:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The readiness endpoint is `/api/v1/health/ready`. Check both database and Redis readiness.

Run `python -m app.worker` separately for scheduled operations. Run `python -m app.mobile_push_worker` only after configuring your private Firebase server credentials and test accounts; it delivers queued notifications.

## Frontend

Use a current Node.js 22 release compatible with the committed Vite version. Install from `frontend` using `npm ci` and retain the committed lockfile.

Copy `frontend/.env.example` to `.env.local`. The local Vite configuration proxies `/api` and `/openapi.json` to `127.0.0.1:8000`. Open `http://localhost:5173` while both local services are running. To expose a development server through a specific hostname, supply it in `VITE_DEV_ALLOWED_HOSTS` and set the bind address explicitly.

For same-origin hosting, use `/api/v1` and configure the reverse proxy to route that prefix and `/openapi.json` to FastAPI. For direct local API access, allow the exact frontend origin in backend CORS. The frontend Dockerfile includes an Nginx configuration that expects an API container named `backend` on the same Docker network; provision that network and API separately.

```bash
npm run dev
npm run build
```

Vite environment values are public client configuration and must never contain credentials. Phone location features need an HTTPS origin and the user's location permission.

## Android and Firebase

See `android/README.md`. Supply your own Firebase Android client file locally, configure the target API host and use an owner-controlled signing key for distributed builds. Supply Firebase Admin credentials only to the backend push worker, never to the Android project.

## Source backup versus operational backup

GitHub stores the application code and documentation. Keep database backups, uploaded files, infrastructure settings, credentials and signing keys in an appropriate private backup process. Those items are intentionally absent from this public repository.
