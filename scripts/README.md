# Scripts

This directory contains utility scripts and entry points for KORA.

## Entry Points

### `run_agent.py`

Bootstrap script for the Python desktop control agent. Runs the FastAPI service with uvicorn.

**Usage:**
```bash
python scripts/run_agent.py
```

**Environment Variables:**
- `KORA_AGENT_HOST` - Host to bind to (default: `127.0.0.1`)
- `KORA_AGENT_PORT` - Port to bind to (default: `8765`)
- `KORA_DATA_DIR` - Data directory for logs (default: current working directory)

**Features:**
- Auto-configures logging to `logs/agent.log`
- Handles frozen executable (PyInstaller) detection
- Gracefully handles missing dependencies

---

## Development Tools

### `local-playwright-server.js`

Standalone Playwright server for development and testing. Runs a headless Chrome instance accessible via Chrome DevTools Protocol (CDP).

**When to Use:**
- Debugging browser automation in isolation
- Testing Playwright scripts without the full KORA UI
- Connecting to Chrome via `--remote-debugging-port`

**Usage:**
```bash
node scripts/local-playwright-server.js
```

**Default:** Listens on `http://127.0.0.1:3001`

**Note:** This is separate from KORA's main browser integration in `agent/tools/browser.py`. Use this if you need to:
- Run Playwright in a separate process
- Test without involving the Gemini Live API
- Debug browser automation logic independently

---

## Start Scripts

For complete KORA startup (both agent and server), see the root directory or refer to the main README.

