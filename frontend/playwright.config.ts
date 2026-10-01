import { defineConfig } from "@playwright/test";

const DB = "/tmp/portfoliolab-e2e.db";
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  use: { baseURL: "http://localhost:3100" },
  webServer: [
    {
      command: `rm -f ${DB} && ../backend/.venv/bin/alembic upgrade head && ../backend/.venv/bin/python -m app.seed --owner-id seed_only && ../backend/.venv/bin/uvicorn app.main:app --port 8100`,
      cwd: "../backend",
      env: { DATABASE_URL: `sqlite:///${DB}`, AUTH_MODE: "dev", CORS_ORIGINS: "http://localhost:3100" },
      url: "http://localhost:8100/api/v1/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npx next dev -p 3100",
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8100", NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "" },
      url: "http://localhost:3100/sign-in",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
