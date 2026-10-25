# RASA Frontend

React/Vite interface for mission building, basket results, explanations, anonymous feedback, and aggregate system insights.

```bash
npm ci
npm run dev
```

The development server proxies `/api` and `/health` to `127.0.0.1:8000`. Set `VITE_API_URL` only when the API is hosted on another origin. A clearly labelled static example remains available when the API is unreachable.

Quality gates: `npm audit`, `npm run lint`, and `npm run build`.
