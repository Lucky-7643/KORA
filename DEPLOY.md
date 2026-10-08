# Deploying KORA

KORA is a Node + Express + Vite app. The production build produces `dist/index.html`,
`dist/assets/*`, and a self-contained `dist/server.cjs` that serves the UI, REST API,
and the `/live` WebSocket.

The repo includes a `Dockerfile`, `.dockerignore`, and `render.yaml` so pretty much any
host (Render, Railway, Fly.io, Hugging Face Spaces, a VPS) can build and run it with no
terminal setup.

## The one thing you must do: set the API key

No source/secret is committed. On every host you must create a **secret environment
variable** named `GEMINI_API_KEY` and paste your Gemini API key as its value
(https://aistudio.google.com/apikey). The app reads it via `process.env.GEMINI_API_KEY`.

## Option A – Render (fastest, free tier available)

1. Push this repo to GitHub.
2. Go to https://dashboard.render.com → **New → Blueprint** → pick the `render.yaml` in
   this repo (or **New → Web Service** → connect the repo).
   - Build command: `npm install && npm run build`
   - Start command: `npm start`
3. Render asks you to fill in `GEMINI_API_KEY` (it is marked as "required, no default").
4. Deploy. When the service shows **Live**, click its URL — KORA opens and runs.

## Option B – Railway (also one-click from GitHub)

1. Push this repo to GitHub.
2. New Project → **Deploy from GitHub repo** → select it.
   Railway auto-detects `package.json` (build = `npm run build`, start = `npm start`).
3. Add the variable `GEMINI_API_KEY`.
4. Click deploy, then open the generated `*.up.railway.app` URL.

## Option C – Docker (works on Fly.io, any VPS, Hugging Face)

```
docker build -t kora .
docker run -p 3000:3000 -e GEMINI_API_KEY=... kora
```

## Expected behavior on a hosted URL

- The voice UI loads: speech + wake word ("Hey Kora") + live Gemini voice work in a
  modern browser with microphone permission.
- **Desktop-control features (opening apps, Spotify, the Windows desktop agent) are
  local-machine tools** and are intentionally unavailable when the site is hosted
  elsewhere — they only run when KORA runs on the Windows machine that has
  `agent/` + `venv/` (see `start_kora.bat`).
- Reminders/memories are stored in the instance's filesystem and are reset when the
  host recycles it — set `GEMINI_API_KEY` and keep secrets only in the platform's env.