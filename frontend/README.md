# R&D Intelligence Agent frontend

Next.js App Router dashboard shell for the R&D Intelligence Agent.

```bash
npm install
npm run dev
```

Copy `.env.example` to `.env.local` when the backend is not available at the
default `http://127.0.0.1:8000` URL. `NEXT_PUBLIC_API_URL` is embedded into the
browser bundle at build time.

Open <http://localhost:3000>. The dashboard can create and list missions through
the backend API; the research workflow itself is not connected yet.

Run the frontend checks with:

```bash
npm test
npm run lint
npm run build
```
