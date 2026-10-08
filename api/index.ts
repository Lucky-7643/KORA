// Vercel Functions entrypoint.
//
// Vercel imports the http server this file exports and serves both the REST
// API and the /live WebSocket upgrade from it (Vercel natively serves
// WebSockets using the `ws` library — public beta, all plans).
//
// src/server/index.ts builds the Express app + routes + WebSocket wiring at
// module load and exports the server; it never calls .listen() while
// process.env.VERCEL === "1", so the platform owns the socket. vercel.json
// rewrites /live and /api/* (plus the SPA fallback) to this function.
import koraServer from "../src/server/index";

export default koraServer;