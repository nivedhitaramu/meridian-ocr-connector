# Meridian Intelligence web app

The Next.js product UI. It shows data from the FastAPI service and holds no business rules.

## Run it

Start the API and PostgreSQL first, as described in the main [README](../README.md), and apply the migrations.

```bash
cp .env.example .env.local
npm install
npm run dev
```

Add your Clerk keys to `.env.local`, then open `http://localhost:3000`.

## Check it

```bash
npm run lint
npm test
npm run build
```

## Rules for this app

- Business decisions stay in the API. The app only displays them.
- API calls run on the server, in `src/lib/api.ts`, using the signed-in user's Clerk token.
- Show only screens that work. Don't add links to pages that don't exist, or demo numbers presented as real.

## Browser tests

```bash
npm run test:e2e
```

These run 14 tests against a real build of this site and the real API, with Chromium, including axe accessibility checks, phone width and keyboard use. They need Tesseract, Poppler, the Python packages and `en_core_web_lg`. Set `E2E_PYTHON` if `python` isn't the right interpreter.

They use the mock model, SQLite, threads in place of Celery, and a stand-in for Clerk (`e2e/clerk-stub`, included only when `E2E_AUTH_STUB=1`). They need no secrets, and they don't test real sign-in.
