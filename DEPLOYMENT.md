# Deploying PortfolioLab (free tiers)

```
Vercel (Next.js)  ──Bearer Clerk JWT──▶  Render (FastAPI, Docker)  ──▶  Supabase (PostgreSQL)
        └──────── sign-in ────────▶ Clerk (issues + signs the JWTs)
```

Why this stack: the API is Python/FastAPI on PostgreSQL, so Supabase supplies the database, Render runs the container, and Vercel hosts Next.js. Firebase is not a fit (no Postgres, no Python hosting). Do the steps in order; each needs values from the previous one.

## 1. Push the repo to GitHub
```bash
git add -A && git commit -m "PortfolioLab" && git branch -M main
git remote add origin https://github.com/<you>/portfoliolab.git && git push -u origin main
```

## 2. Database — Supabase
1. supabase.com → **New project** (pick a region near you, save the database password).
2. **Connect** button → **Connection string** → choose **Session pooler** (port 5432; works over IPv4, which Render needs).
3. Copy it and put your password in: `postgresql://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   The API rewrites `postgresql://` to the psycopg driver itself. Special characters in the password must be URL-encoded.

You don't create tables by hand — the API container runs Alembic migrations on every start.

## 3. Auth — Clerk
1. clerk.com → **Create application** (enable Email and/or Google).
2. **API keys**: copy the *Publishable key* (`pk_…`) and *Secret key* (`sk_…`).
3. Note your **Frontend API URL** (shown on the API keys page, e.g. `https://sweet-bee-12.clerk.accounts.dev`). Then:
   - `CLERK_ISSUER` = that URL
   - `CLERK_JWKS_URL` = that URL + `/.well-known/jwks.json`

## 4. API — Render
1. render.com → **New → Blueprint** → select your repo (it reads [render.yaml](render.yaml)). Or **New → Web Service**, runtime *Docker*, root directory `backend`.
2. Set environment variables:

| Key | Value |
|---|---|
| `AUTH_MODE` | `clerk` (**never `dev`** in production) |
| `DATABASE_URL` | the Supabase string from step 2 |
| `CLERK_ISSUER` / `CLERK_JWKS_URL` | from step 3 |
| `CORS_ORIGINS` | your Vercel URL (fill in after step 5, then redeploy) |

3. Deploy. On start the container runs `alembic upgrade head`, loads the sample market data (idempotent), then starts uvicorn.
4. Verify: `https://<your-service>.onrender.com/api/v1/health` → `{"status":"ok"}`, and `/docs` shows the API.

Free Render services sleep after ~15 min idle; the first request then takes ~30–60 s. Supabase free projects pause after a week of inactivity (resume from the dashboard).

## 5. Frontend — Vercel
1. vercel.com → **Add New → Project** → import the repo, set **Root Directory** to `frontend`.
2. Environment variables:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<your-service>.onrender.com` (no trailing slash) |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_…` |
| `CLERK_SECRET_KEY` | `sk_…` |

3. Deploy, copy the resulting URL, and set it as `CORS_ORIGINS` on Render (then redeploy the API).
4. In Clerk → **Domains / Paths**, add your Vercel domain if prompted.

## 6. Verify end to end
Open the Vercel URL → sign up → **Load demo portfolio** → the dashboard should show the "Sample data" badge. If not:

| Symptom | Fix |
|---|---|
| Browser console CORS error | `CORS_ORIGINS` must exactly equal the Vercel origin (scheme + host, no trailing slash) |
| 401 `invalid_token` | `CLERK_ISSUER` must match the token's issuer exactly; check `CLERK_JWKS_URL` |
| 500 `auth_misconfigured` | `CLERK_ISSUER` / `CLERK_JWKS_URL` missing on Render |
| API fails at boot with connection errors | Use the Supabase *Session pooler* URL; re-check the password encoding |
| Slow first load | Free-tier cold start, see above |

## Alternatives
- **Railway / Fly.io** instead of Render: same Dockerfile, same env vars (the container honours `$PORT`).
- **Supabase only for hosting Postgres** is intentional: its auth/storage features aren't used because Clerk handles sign-in and the API owns the data access.
- **All-local with Docker:** `docker compose up --build` (see README).

## Production checklist
- [ ] `AUTH_MODE=clerk` on the API; no `dev:` tokens accepted.
- [ ] Secrets only in Render/Vercel env settings, never in git (`.env` is ignored).
- [ ] `CORS_ORIGINS` limited to your frontend origin.
- [ ] Take screenshots (`SCREENSHOTS=1 npx playwright test screenshots`) and add the live URL to the README.
