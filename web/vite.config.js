import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const REPO_ROOT = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig(({ mode }) => {
  // Read the repo-root .env (§4.3). Values are used here in Node only; the
  // client receives just the two service URLs through `define` below.
  const env = loadEnv(mode, REPO_ROOT, "");
  const webPort = Number(env.WEB_PORT || 5173);
  const webOrigin = `http://localhost:${webPort}`;
  const webauthnOrigin = env.WEBAUTHN_ORIGIN || webOrigin;

  // Passkeys fail silently if the page origin and the issuer's expected
  // origin differ (docs/CONTEXT.md §12). Refuse to start instead.
  if (webauthnOrigin !== webOrigin) {
    throw new Error(`WEBAUTHN_ORIGIN is ${webauthnOrigin} but the web app serves ${webOrigin}. Fix .env.`);
  }

  return {
    plugins: [react()],
    define: {
      __MERCHANT_URL__: JSON.stringify(`http://localhost:${env.MERCHANT_PORT || 8000}`),
      __ISSUER_URL__: JSON.stringify(`http://localhost:${env.ISSUER_PORT || 8100}`),
    },
    server: {
      host: "localhost", // never 127.0.0.1: mixing the two breaks WebAuthn
      port: webPort,
      strictPort: true, // a silent port change would break the origin check
    },
  };
});
