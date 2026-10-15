import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The build goes straight into the Python package, so `agatesim serve` ships it.
// In development (`npm run dev`), API calls are proxied to `agatesim serve` on :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/agatesim/server/static",
    emptyOutDir: true,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "node",
  },
});
