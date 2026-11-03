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
