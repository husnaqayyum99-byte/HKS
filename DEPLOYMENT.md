# Local Setup and Deployment

## Environment

Copy the example files and edit the copies locally. Never commit `.env` files.

```powershell
Copy-Item bknd/.env.example bknd/.env
Copy-Item apna-wakeel-frontend/.env.example apna-wakeel-frontend/.env
```

Backend variables:

- `DATABASE_URL`: `sqlite:///./app.db` locally; use a PostgreSQL SQLAlchemy URL in production, preferably `postgresql+psycopg://...` with the provider's required TLS options.
- `SUPABASE_URL` and `SUPABASE_KEY`: Supabase project URL and publishable/anon key. Do not use a service-role key for browser-visible code.
- `GROQ_API_KEY` and optional `GROQ_MODEL`: AI provider credentials and model.
- If a Groq key has ever been exposed in source, logs, screenshots, or shared materials, revoke it and create a replacement. Keep the replacement only in the backend environment; never place it in Vite variables or commit it.
- `FRONTEND_URL`: frontend origin, without a trailing slash; used for signup confirmation and password recovery redirects.
- `CORS_ORIGINS`: comma-separated exact frontend origins. Use local origins in development and only the deployed frontend origin(s) in production. Do not use `*`.

Frontend variable:

- `VITE_API_URL`: FastAPI base URL. Set it before building the production frontend; the localhost fallback is development-only.
- `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`: public Supabase project URL and publishable/anon key used by the PKCE password-recovery flow. These are public client values, not service-role credentials.

## Supabase Redirects

In Supabase Auth URL Configuration, set the Site URL to the frontend origin. Add these exact redirect URLs to the allow list:

- `http://127.0.0.1:5173/login`
- `http://127.0.0.1:5173/reset-password`
- `https://<your-frontend-domain>/login`
- `https://<your-frontend-domain>/reset-password`

Use the actual deployed HTTPS domain in place of the placeholder. `FRONTEND_URL` must match that origin. Test signup confirmation and password recovery after configuring the allow list; this repository cannot verify project-dashboard settings.

Password-recovery requests use the configured PKCE Supabase browser client so the one-time verifier stays in that browser. The reset page accepts the Supabase recovery session and calls Supabase Auth to update the password; reset tokens are not written to the app's local session storage.

## Local Development

From the repository root, install and migrate the backend, then start it:

```powershell
Set-Location bknd
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location apna-wakeel-frontend
npm.cmd ci
npm.cmd run dev
```

Frontend: `http://127.0.0.1:5173`. Backend health: `http://127.0.0.1:8000/api/health`.

## Public legal analysis

The public legal-path page submits `POST /api/public-analysis`. It accepts a problem description, the selected language (`en`, `ur`, or `roman_urdu`), and up to ten recent user/assistant turns for a follow-up. Requests are bounded to 8,000 characters per message and are not saved to a user account. The endpoint uses the same intake, classification, research, retrieval, verification, and response pipeline as authenticated conversations; it does not return a fallback/demo answer when Groq or official evidence is unavailable.

The response includes the problem understanding, legal area, jurisdiction, supported steps/documents/authorities, unresolved claims, and official evidence linked to claims. The anonymous endpoint incurs provider usage, so production deployments should place suitable abuse/rate controls at the API gateway or hosting layer.

## Production Build and Startup

Set backend environment variables in the hosting platform, configure PostgreSQL and the frontend origin, then run migrations before starting the API:

```powershell
Set-Location bknd
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `VITE_API_URL` to the public HTTPS API URL in the frontend build environment:

```powershell
Set-Location apna-wakeel-frontend
npm.cmd ci
npm.cmd run build
```

Deploy the generated `dist` directory to a static host configured to rewrite application routes (including `/login`, `/forgot-password`, and `/reset-password`) to `index.html`. The API host must allow only the deployed frontend origin in `CORS_ORIGINS`.

## Database and Documents

Alembic owns the production schema. Run `python -m alembic upgrade head` for every release that changes the schema; do not rely on application startup to migrate PostgreSQL. SQLite local startup initializes its basic schema for convenience, and the migration can also upgrade a legacy SQLite database.

Document uploads are limited to PDF and DOCX, with text extraction and no OCR for scanned PDFs. Files currently live under `bknd/uploads`; production hosting needs a persistent, access-controlled volume. Back up the database and file volume together. Do not use ephemeral server storage for user documents.

## Readiness Limits

The repository provides no production hosting provider configuration. Before launch, verify the production PostgreSQL connection and migrations, Supabase confirmation/reset redirects, Groq quota/model access, persistent document storage, and the deployed domain's CORS/preflight behavior. A successful local build is not a substitute for those checks.