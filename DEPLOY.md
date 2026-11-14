# Deploying the backend to Railway

The backend is `recall/` served by `python -m recall.cloud` (Docker, see `Dockerfile`).
The Expo app talks to it over `wss://<railway-domain>/ws?token=<RECALL_TOKEN>`.

## Pipeline (`.github/workflows/backend.yml`)

- **Pull request** touching `recall/`, `Dockerfile`, `railway.json`, `requirements-server.txt`:
  compile, boot the server, check `/healthz` and that requests without the token get 401, Docker build.
- **Push to `main`**: same checks, then `railway up --ci` deploys to the Railway service.

## One-time setup

1. **Railway**: create a project, add an empty service (e.g. `backend`).
   - Service → Settings → Networking → *Generate Domain*.
   - Service → Variables: `RECALL_TOKEN` (long random string), `GEMINI_API_KEY`, `RECALL_DB=/data/recall.db`.
   - Service → *Attach volume* mounted at `/data` (otherwise memories vanish on each deploy).
   - Project → Settings → Tokens → create a **project token** for the production environment.
2. **GitHub** (repo → Settings → Secrets and variables → Actions):
   - Secret `RAILWAY_TOKEN` = the project token.
   - Variable `RAILWAY_SERVICE` = the service name (`backend`).
   - Optional: Settings → Environments → `production` with required reviewers to gate deploys.
3. **Expo**: set `EXPO_PUBLIC_API_URL=https://<railway-domain>` (and the token) in the app's env / `eas.json`.

Do **not** also turn on Railway's own GitHub auto-deploy for this service, or every push deploys twice
(and skips the CI gate).

## Run it locally like Railway does

```bash
RECALL_TOKEN=dev-token-0123456789 RECALL_DB=./recall.db PORT=8080 python -m recall.cloud
```
